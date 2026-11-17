"""Build tetrix brazing jigs (default 130.9 mm level 1), verify, render, zip -> /workspace/exports/tetrix_jig/."""
import os, json, sys, zipfile
from pathlib import Path
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, trimesh, pyrender
from PIL import Image, ImageDraw
import tetrix_jig as T
from moai_render import look_at, board

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/exports/tetrix_jig/v2_snap_1p88"); OUT.mkdir(parents=True, exist_ok=True)
MEDIA = Path(__file__).resolve().parents[1] / "media"
p = T.DEFAULT
JIG, CU = (0.35, 0.55, 0.78), (0.80, 0.45, 0.22)
_R = {}

def render(items, path, direction, title="", size=(900, 800), target=None, mag=None):
    allm = trimesh.util.concatenate([m for m, _ in items])
    target = allm.bounds.mean(0) if target is None else np.asarray(target)
    mag = mag or 0.62 * np.ptp(allm.bounds, 0).max()
    if size not in _R: _R[size] = pyrender.OffscreenRenderer(*size)
    sc = pyrender.Scene(bg_color=[0.9, 0.93, 0.96, 1], ambient_light=[0.2] * 3)
    for m, col in items:
        mat = pyrender.MetallicRoughnessMaterial(baseColorFactor=[*col, 1], metallicFactor=0.0, roughnessFactor=0.8)
        sc.add(pyrender.Mesh.from_trimesh(m, material=mat, smooth=False))
    d = np.asarray(direction, float); d /= np.linalg.norm(d)
    sc.add(pyrender.OrthographicCamera(xmag=mag * size[0] / size[1], ymag=mag, znear=1, zfar=3000), pose=look_at(target + d * 900, target))
    sc.add(pyrender.DirectionalLight(intensity=3.0), pose=look_at(target + 600 * (d + np.array([0.4, 0, 0.7])), target))
    sc.add(pyrender.DirectionalLight(intensity=1.2), pose=look_at(target + 600 * (d + np.array([-0.6, 0, -0.2])), target))
    c, _ = _R[size].render(sc)
    im = Image.fromarray(c); ImageDraw.Draw(im).text((10, 10), title, fill=(0, 0, 0)); im.save(path)
    return path

out, info = T.build(p)
ver = {"params": T.asdict(p), "dims": T.dims_dict(p), "bed": f"{T.BED:g} x {T.BED:g} usable, parts kept <= {T.BED_KEEP:g} mm",
       "min_joint_clearance_required_mm": T.MIN_JOINT_CLEAR}
files = {}
for k, tm in out.items():
    f = OUT / f"{k}.stl"; tm.export(f); files[k] = f
re = {k: trimesh.load(f) for k, f in files.items()}          # verify what was written
ver["parts"] = T.verify(p, re, info)

dirv = (1, -1.4, 0.95)
# 1 gauge with a short rod (in row A, protruding past the cut face) and a long rod
g = re["rod_length_gauge"]; gi = info["rod_length_gauge"]; rc = p.rod_d / 2; zc = gi["zc"]
ra = T.rods_mesh([((gi["stop"], gi["rows_y"]["A"], zc), (gi["stop"] + gi["short_cut"] + 12, gi["rows_y"]["A"], zc))], p.rod_d)
rb = T.rods_mesh([((gi["stop"], gi["rows_y"]["B"], zc), (gi["stop"] + gi["long_cut"], gi["rows_y"]["B"], zc))], p.rod_d)
render([(g, JIG), (ra, CU), (rb, CU)], OUT / "rod_length_gauge.png", dirv, "rod_length_gauge.stl: A short cut (stop->step face), B long cut 129.9, C straightening")
# 2 single tetra jig with rods
tj = re["single_tetra_jig"]; trods = T.rods_mesh(info["single_tetra_jig"]["rods"], p.rod_d)
render([(tj, JIG), (trods, CU)], OUT / "single_tetra_jig_loaded.png", dirv, "single_tetra_jig.stl + 6 rods (64.45 mm) in place")
render([(tj, JIG)], OUT / "single_tetra_jig.png", dirv, "single_tetra_jig.stl (empty)")
render([(tj, JIG), (trods, CU)], OUT / "single_tetra_jig_top.png", (0, 0, 1), "single_tetra_jig top view: joints overhang the plate")
# 3 assembly plate with 4 tetras
ak = [k for k in out if k.startswith("assembly_plate")][0]
aj = re[ak]; arods = T.rods_mesh(info[ak]["rods"], p.rod_d)
render([(aj, JIG), (arods, CU)], OUT / "assembly_plate_loaded.png", dirv, f"{ak}.stl + 4 tied tetrahedra")
render([(aj, JIG)], OUT / "assembly_plate.png", dirv, f"{ak}.stl (empty)")
render([(aj, JIG), (arods, CU)], OUT / "assembly_plate_side.png", (1, -0.2, 0.15), "side: top tetra on 3 posts + 3 lower apexes")
# overview
rr = re["rods_reference"]
render([(rr, CU)], OUT / "tetrix_overview.png", dirv, "rods_reference.stl: level-1 tetrix 130.9 mm, 24 rods, 10 joints")
board([OUT / "rod_length_gauge.png", OUT / "single_tetra_jig_loaded.png", OUT / "assembly_plate_loaded.png", OUT / "tetrix_overview.png"],
      OUT / "tetrix_jig_board.png", f"Tetrix brazing jig set v2 snap (130.9 mm, level 1, rod {p.rod_d:g}, seat {p.rod_d + p.clearance:g}, mouth {T._mouth(p):g})", cols=2)
(OUT / "verification.json").write_text(json.dumps(ver, indent=2, default=float))
# close-up cross-sections: a base cradle of the single-tetra jig and gauge row A, with the rod in its seat
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
def section(ax, mesh, m, u, title, rod_c, top_ax):
    m = np.asarray(m, float); u = np.asarray(u, float); u /= np.linalg.norm(u)
    v = np.array([-u[1], u[0], 0.0]); v /= np.linalg.norm(v); z = np.cross(u, v)
    sec = mesh.section(plane_origin=m, plane_normal=u)
    from shapely.geometry import Polygon
    from shapely.ops import unary_union, polygonize
    lines = [np.column_stack([(e - rod_c) @ v, (e - rod_c) @ z]) for e in sec.discrete]
    polys = list(polygonize([__import__("shapely.geometry", fromlist=["LineString"]).LineString(l) for l in lines]))
    geom = unary_union(polys)
    win = __import__("shapely.geometry", fromlist=["box"]).box(-4.5, -4.5, 4.5, top_ax + 0.8)
    for g in getattr(geom.intersection(win), "geoms", [geom.intersection(win)]):
        if g.geom_type == "Polygon":
            ax.fill(*g.exterior.xy, color=(0.35, 0.55, 0.78)); [ax.fill(*h.xy, color="white") for h in g.interiors]
    S = T.snap_profile(p, top_ax)
    ax.add_patch(plt.Circle((0, 0), p.rod_d / 2, color=(0.80, 0.45, 0.22), zorder=3))
    ax.add_patch(plt.Circle((0, 0), S["rs"], fill=False, ls="--", lw=0.8, color="k", zorder=4))
    ax.annotate("", xy=(-S["rm"], S["z_close"] + 0.15), xytext=(S["rm"], S["z_close"] + 0.15), arrowprops=dict(arrowstyle="<->", lw=0.8))
    ax.text(0, S["z_land"] + 1.0, f"mouth {2 * S['rm']:.2f}", ha="center", fontsize=8)
    ax.text(0, -S["rs"] - 0.55, f"seat Ø{2 * S['rs']:.2f} (dashed), rod Ø{p.rod_d:g}", ha="center", fontsize=8)
    ax.text(-4.3, top_ax + 0.3, f"lip {p.lip_t:g} thick, relief {p.relief_w:g}; wrap {S['seat_wrap_deg']:.0f}°;"
            f" {max(0, (p.rod_d - 2 * S['rm']) / 2):.3f} mm/side", fontsize=7)
    ax.set_title(title, fontsize=9); ax.set_aspect("equal"); ax.set_xlim(-4.5, 4.5); ax.set_ylim(-4.5, top_ax + 0.8)
    ax.grid(alpha=0.3); ax.set_xlabel("mm")
fig, axs = plt.subplots(1, 2, figsize=(12, 6))
a0, b0 = info["single_tetra_jig"]["rods"][0]
mid = (np.asarray(a0) + np.asarray(b0)) / 2
section(axs[0], tj, mid, np.asarray(b0) - np.asarray(a0), "single_tetra_jig: base cradle cross-section", mid, (p.rod_d + p.clearance) / 2 + T.CRADLE_TOP)
gm = np.array([gi["stop"] + gi["short_cut"] / 2, gi["rows_y"]["A"], gi["zc"]])
section(axs[1], g, gm, (1, 0, 0), "rod_length_gauge: row A cross-section", gm, 8.0 - gi["zc"])
fig.suptitle(f"Snap seat close-up (rod {p.rod_d:g} mm, seat {p.rod_d + p.clearance:g}, mouth {T._mouth(p):g})")
fig.savefig(OUT / "snap_channel_section.png", dpi=130, bbox_inches="tight")
uax = (np.asarray(b0) - np.asarray(a0)); uax /= np.linalg.norm(uax)
outw = mid - np.r_[tj.bounds.mean(0)[:2], mid[2]]; outw[2] = 0; outw /= np.linalg.norm(outw)
render([(tj, JIG), (trods, CU)], OUT / "single_tetra_jig_closeup.png", 0.9 * uax + 0.5 * outw + np.array([0, 0, 0.55]),
       "close-up: 1.88 rod snapped into a base cradle (lips + relief slots)", target=mid, mag=9.0)
print(json.dumps(ver, indent=1, default=float))
