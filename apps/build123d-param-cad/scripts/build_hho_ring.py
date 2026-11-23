"""Build the HHO vortex nozzle ring (PLA cold-gas test fixture + metal-ready STEP), verify, render.
Usage: build_hho_ring.py [OUT]   (default /workspace/exports/hho_vortex_ring/v1)"""
import os, json, sys
from pathlib import Path
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, trimesh, pyrender
from PIL import Image, ImageDraw
import hho_ring as H
from moai_render import look_at, board

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/exports/hho_vortex_ring/v1"); OUT.mkdir(parents=True, exist_ok=True)
RING, GAS, BRASS, JET = (0.30, 0.52, 0.80), (0.95, 0.55, 0.15), (0.85, 0.68, 0.20), (0.85, 0.10, 0.10)
_R = {}


def render(items, path, direction, title="", size=(900, 800), target=None, mag=None, up=(0, 0, 1)):
    allm = trimesh.util.concatenate([m for m, _ in items])
    target = allm.bounds.mean(0) if target is None else np.asarray(target)
    mag = mag or 0.6 * np.ptp(allm.bounds, 0).max()
    if size not in _R: _R[size] = pyrender.OffscreenRenderer(*size)
    sc = pyrender.Scene(bg_color=[0.95, 0.95, 0.97, 1], ambient_light=[0.3] * 3)
    for m, col in items:
        mat = pyrender.MetallicRoughnessMaterial(baseColorFactor=[*col, 1], metallicFactor=0.0, roughnessFactor=0.7)
        sc.add(pyrender.Mesh.from_trimesh(m, material=mat, smooth=False))
    d = np.asarray(direction, float); d /= np.linalg.norm(d)
    sc.add(pyrender.OrthographicCamera(xmag=mag * size[0] / size[1], ymag=mag, znear=1, zfar=3000), pose=look_at(target + d * 900, target, up))
    sc.add(pyrender.DirectionalLight(intensity=3.0), pose=look_at(target + 600 * (d + np.array([0.4, 0.2, 0.7])), target, up))
    sc.add(pyrender.DirectionalLight(intensity=1.4), pose=look_at(target + 600 * (d + np.array([-0.6, 0, -0.4])), target, up))
    c, _ = _R[size].render(sc)
    im = Image.fromarray(c); dr = ImageDraw.Draw(im)
    for i, line in enumerate(title.split("\n")): dr.text((10, 10 + 14 * i), line, fill=(0, 0, 0))
    im.save(path); return str(path)


p = H.DEFAULT
res = H.build(p); L = res["L"]
stl, step = H.export(res, OUT)
ring = trimesh.load(stl); ring.merge_vertices()
ver = H.verify(p, res)
# re-check the exported STL itself
ver["exported_stl"] = dict(watertight=bool(ring.is_watertight), bodies=len(ring.split(only_watertight=False)),
                           volume_mm3=round(float(ring.volume), 2))
cav = H.to_mesh(res["cavity"])
cav.export(OUT / "hho_vortex_ring_gas_cavity_reference.stl")
tips, jets = H.tip_meshes(p, L), H.jet_meshes(p, L, extra=2.0)
core = trimesh.creation.annulus(r_min=H.jets(p, L)["vortex_core_radius_mm"] - 0.25,
                                r_max=H.jets(p, L)["vortex_core_radius_mm"] + 0.25, height=0.3)
core.apply_translation((0, 0, H.jets(p, L)["focal_z_mm"]))
jets = trimesh.util.concatenate([jets, core])
rep = H.report(p)
J = rep["jets"]
direct = H.RingParams(manifold="direct")
rep_direct = H.path_lengths(direct)
alt = {}
for key, kw in (("tube_5_16", dict(tube=list(H.BARBS)[1])), ("tip_ks8126", dict(tip="ks8126", shank_od=H.TIPS["ks8126"]["od"])),
                ("direct", dict(manifold="direct"))):
    q = H.RingParams(**kw); alt[key] = dict(params=kw, verify=H.verify(q, H.build(q)), paths=H.path_lengths(q))

imgs = []
cap = f"Tilt {p.tilt_deg:g} deg DOWN, swirl {p.swirl_deg:g} deg. COLD-GAS TEST FIXTURE ONLY - never light the PLA ring."
imgs.append(render([(ring, RING), (tips, BRASS), (jets, JET)], OUT / "iso.png", (1, -1.2, 0.9),
                   f"Iso: ring + 4 brass tips + jet lines (red)\n{cap}"))
imgs.append(render([(ring, RING), (tips, BRASS), (jets, JET)], OUT / "top.png", (0, 0, 1),
                   f"Top: jets swirl CCW round a {2*J['vortex_core_radius_mm']:.1f} mm vortex core", up=(0, 1, 0)))
half = ring.slice_plane((0, 0, 0), (0, 1, 0), cap=True)
imgs.append(render([(half, RING), (tips, BRASS), (jets, JET)], OUT / "side.png", (0, -1, 0.0001),
                   f"Side (half-section): 4 jets tilt {p.tilt_deg:g} deg DOWN and converge on a "
                   f"{2*J['vortex_core_radius_mm']:.1f} mm vortex core\n{J['focal_depth_below_ring_mm']:.1f} mm below the ring "
                   "bottom (red ring) - tornado runs on down below the ring", target=(5, 0, 6), mag=24))
imgs.append(render([(ring, RING), (tips, BRASS), (jets, JET)], OUT / "bottom.png", (0.15, -0.35, -1),
                   "From below (flame side)"))
# cutaway 1: horizontal cut through the plenum centre, looking down
low = ring.slice_plane((0, 0, L["z_p"]), (0, 0, -1), cap=True)
imgs.append(render([(low, RING), (tips, BRASS)], OUT / "cutaway_plenum.png", (0, 0, 1),
                   f"Cutaway at plenum centre z={L['z_p']:.2f}: full-ring plenum + 4 feeds", up=(0, 1, 0)))
# cutaway 2: vertical half-section (keep y>0 ... show x-z through the inlet), plus the gas cavity
imgs.append(render([(half, RING), (tips, BRASS)], OUT / "cutaway_section.png", (0.25, -1, 0.35),
                   "Half-section: barb bore -> runner -> distribution arc (upper) / plenum (lower) -> feed -> socket"))
imgs.append(render([(cav, GAS), (tips, BRASS)], OUT / "gas_path.png", (1, -1.2, 0.9),
                   f"Gas cavity (one connected body): paths equal to {rep['path_balance']['max_minus_min_mm']} mm"))
board(imgs, OUT / "hho_vortex_ring_board.png", "HHO vortex nozzle ring v1 - PLA COLD-GAS TEST FIXTURE ONLY (metal STEP for the real head)", cols=4)
summary = dict(params=H.params_dict(p), report=rep, verify=ver, direct_manifold_paths=rep_direct, variants=alt,
               files=dict(stl=str(stl), step=str(step), cavity=str(OUT / "hho_vortex_ring_gas_cavity_reference.stl"),
                          images=imgs, board=str(OUT / "hho_vortex_ring_board.png")),
               tip=H.TIPS[p.tip], safety=H.SAFETY)
(OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
print(json.dumps(dict(verify=ver, jets=J, paths=rep["path_balance"], direct=rep_direct,
                      variants={k: (v["verify"]["ok"], v["verify"]["size_mm"]) for k, v in alt.items()}), indent=1))
