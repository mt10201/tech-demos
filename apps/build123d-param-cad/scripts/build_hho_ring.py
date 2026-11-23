"""Build the HHO vortex nozzle ring (PLA cold-gas test fixture + metal-ready STEP), verify, render.
Usage: build_hho_ring.py [OUT]   (default /workspace/exports/hho_vortex_ring/v2_top_round)

v1 (sharp top-inner edge) lives in /workspace/exports/hho_vortex_ring/v1 and must not be overwritten.
This script writes the current defaults (rounded 2.5 mm top inner edge).
"""
import os, json, sys, math, hashlib
from pathlib import Path
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, trimesh, pyrender
from PIL import Image, ImageDraw
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, Arc, Rectangle
from matplotlib.lines import Line2D
import hho_ring as H
from moai_render import look_at, board

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/exports/hho_vortex_ring/v2_top_round")
OUT.mkdir(parents=True, exist_ok=True)
# Never clobber the frozen v1 export, even if someone passes that folder by mistake.
if OUT.resolve() == Path("/workspace/exports/hho_vortex_ring/v1").resolve():
    raise SystemExit("Refusing to write into the frozen v1 export folder. Pass a different OUT path.")
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


def _xy(R, deg):
    a = math.radians(deg)
    return R * math.cos(a), R * math.sin(a)


def _arrow(ax, x0, y0, x1, y1, color, lw=1.8, ms=12):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=ms,
                                 lw=lw, color=color, zorder=6, shrinkA=0, shrinkB=0))


def _arc_arrows(ax, R, a0, a1, color, n=3, lw=1.8, ms=12, inward=0.0):
    """Arrows along a circular arc from a0 to a1 (degrees, CCW if a1>a0)."""
    r = R + inward
    span = a1 - a0
    for i in range(n):
        t0 = a0 + span * (i + 0.08) / n
        t1 = a0 + span * (i + 0.92) / n
        _arrow(ax, *_xy(r, t0), *_xy(r, t1), color, lw=lw, ms=ms)


def gas_path_labeled(p, L, path, paths_mm=80.4):
    """Top-down labelled schematic of the split manifold: barb, 180° arc, risers, plenum, four tips."""
    Rp, Rout, Rcyl = p.R_plenum, L["R_out"], L["r_cyl"]
    flare = Rcyl + L["top_edge_size"]
    Rb, br = L["R_barb"], L["boss_r"]
    COL_BODY, COL_PLEN, COL_ARC, COL_RISER = "#d7dde5", "#0e7a6c", "#e67e22", "#7d3c98"
    COL_BARB, COL_TIP, COL_PATH, COL_INK = "#1f4e79", "#c9a227", "#c0392b", "#1a1a1a"
    fig, ax = plt.subplots(figsize=(9, 8), dpi=100)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f7f8fa")
    # Ring body (top face) and flared inner bore
    ax.add_patch(Circle((0, 0), Rout, facecolor=COL_BODY, edgecolor="#7a8490", lw=1.2, zorder=0))
    ax.add_patch(Circle((0, 0), flare, facecolor="#f7f8fa", edgecolor="#7a8490", lw=1.0, zorder=1))
    # Inlet boss + barb at 0° (+X)
    ax.add_patch(Circle((Rb, 0), br, facecolor=COL_BODY, edgecolor="#7a8490", lw=1.0, zorder=0))
    ax.add_patch(Rectangle((Rout - 1, -br), Rb - Rout + 1, 2 * br, facecolor=COL_BODY, edgecolor="none", zorder=0))
    # barb neck (schematic)
    ax.add_patch(Circle((Rb, 0), L["barb"]["root"] / 2, facecolor="#e8eef4", edgecolor=COL_BARB, lw=1.6, zorder=3))
    ax.plot([Rb, Rb + 6], [0, 0], color=COL_BARB, lw=6, solid_capstyle="round", zorder=3)
    box = dict(boxstyle="round,pad=0.22", fc="white", ec="none", alpha=0.9)
    ax.annotate("Vinyl barb\n(inlet) at 0°", xy=(Rb + 3, 0.4), xytext=(Rb + 2, 12.2),
                ha="center", va="bottom", fontsize=8, color=COL_BARB, fontweight="bold",
                arrowprops=dict(arrowstyle="-", color=COL_BARB, lw=0.8), bbox=box, zorder=8)

    # Lower plenum — full ring
    ax.add_patch(Circle((0, 0), Rp, facecolor="none", edgecolor=COL_PLEN, lw=5.5, zorder=2))
    ax.annotate("Plenum\n(full ring, lower)", xy=_xy(Rp, 200), xytext=_xy(Rp + 10.2, 208),
                ha="center", va="center", fontsize=8, color=COL_PLEN, fontweight="bold",
                arrowprops=dict(arrowstyle="-", color=COL_PLEN, lw=0.8), bbox=box, zorder=8)

    # Upper 180° distribution arc on the +X half, -90° → +90°
    ax.add_patch(Arc((0, 0), 2 * Rp, 2 * Rp, theta1=-90, theta2=90,
                     color=COL_ARC, lw=3.4, zorder=4))
    ax.annotate("180° distribution arc\n(upper)", xy=_xy(Rp, -25), xytext=(23.5, -8.5),
                ha="center", va="top", fontsize=8, color=COL_ARC, fontweight="bold",
                arrowprops=dict(arrowstyle="-", color=COL_ARC, lw=0.8), bbox=box, zorder=8)

    # Radial runner, barb axis → distribution arc
    _arrow(ax, Rb - 1.2, 0, Rp + 1.2, 0, COL_PATH, lw=2.0, ms=14)
    ax.text((Rb + Rp) / 2, -2.0, "runner", ha="center", va="top", fontsize=7, color=COL_PATH)

    # Risers at 90° and 270°
    for ang, label, offset in ((90, "Riser at 90°\n(feeds 45° and 135° equally)", (5.2, 6.4)),
                               (-90, "Riser at 270°\n(feeds 225° and 315° equally)", (5.2, -7.6))):
        x, y = _xy(Rp, ang)
        ax.add_patch(Circle((x, y), p.riser_r + 0.7, facecolor=COL_RISER, edgecolor="white", lw=1.2, zorder=7))
        ax.annotate(label, xy=(x, y), xytext=(x + offset[0], y + offset[1]),
                    ha="left", va="center", fontsize=8, color=COL_RISER, fontweight="bold",
                    arrowprops=dict(arrowstyle="-", color=COL_RISER, lw=0.8), bbox=box, zorder=8)

    # Arrows along the distribution arc: 0° → 90° and 0° → 270°
    _arc_arrows(ax, Rp, 8, 78, COL_PATH, n=2, lw=1.6, ms=11, inward=0.0)
    _arc_arrows(ax, Rp, -8, -78, COL_PATH, n=2, lw=1.6, ms=11, inward=0.0)

    # Arrows along the plenum: each riser → its two tips (slightly inside the plenum stroke)
    _arc_arrows(ax, Rp, 90, 50, COL_PLEN, n=1, lw=1.7, ms=11, inward=-1.6)   # 90 → 45
    _arc_arrows(ax, Rp, 90, 130, COL_PLEN, n=1, lw=1.7, ms=11, inward=-1.6)  # 90 → 135
    _arc_arrows(ax, Rp, -90, -50, COL_PLEN, n=1, lw=1.7, ms=11, inward=-1.6)  # 270 → 315
    _arc_arrows(ax, Rp, -90, -130, COL_PLEN, n=1, lw=1.7, ms=11, inward=-1.6) # 270 → 225

    # Four brass tips at 45/135/225/315
    tip_lbl_xy = {45: (17.0, 17.8), 135: (-22.0, 16.2), 225: (-22.0, -18.0), 315: (17.0, -18.5)}
    for k in range(p.n_tips):
        ang = H.tip_angle(p, k)
        # socket mouth in the top view
        E = L["mouths"][k]
        T = L["tips"][k]
        ax.plot([E[0], T[0]], [E[1], T[1]], color=COL_TIP, lw=3.2, solid_capstyle="round", zorder=7)
        ax.add_patch(Circle((E[0], E[1]), 1.15, facecolor=COL_TIP, edgecolor="#6b5408", lw=0.6, zorder=8))
        ax.annotate(f"Tip {k + 1}  at {ang:g}°\npath  {paths_mm:.1f} mm",
                    xy=(E[0], E[1]), xytext=tip_lbl_xy[ang],
                    ha="left", va="center",
                    fontsize=7.5, color="#6b5408", fontweight="bold",
                    arrowprops=dict(arrowstyle="-", color="#6b5408", lw=0.7), bbox=box, zorder=8)

    # Title, subtitle, legend
    ax.set_title("HHO vortex ring  —  equal gas paths  (top view)", fontsize=12, pad=10, color=COL_INK, fontweight="bold")
    ax.text(0, 28.8,
            f"Barb  →  runner  →  180° distribution arc  →  two risers (90° / 270°)  →  full plenum  →  four tips.\n"
            f"Every inlet-to-tip centre-line is {paths_mm:.1f} mm.  Each riser feeds two tips equally.",
            ha="center", va="top", fontsize=8, color=COL_INK)

    handles = [
        Line2D([0], [0], color=COL_BARB, lw=3, label="Vinyl barb (inlet)"),
        Line2D([0], [0], color=COL_ARC, lw=3, label="180° distribution arc (upper)"),
        Line2D([0], [0], color=COL_RISER, lw=0, marker="o", markersize=8, label="Risers at 90° and 270°"),
        Line2D([0], [0], color=COL_PLEN, lw=3, label="Plenum (full ring, lower)"),
        Line2D([0], [0], color=COL_TIP, lw=3, label="Brass tips at 45 / 135 / 225 / 315°"),
        Line2D([0], [0], color=COL_PATH, lw=2, label=f"Gas-flow direction  ({paths_mm:.1f} mm each)"),
    ]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(-0.04, -0.14), frameon=True,
              fontsize=7, ncol=2, framealpha=0.95, edgecolor="#c8cdd3")

    ax.set_aspect("equal")
    ax.set_xlim(-33, 39)
    ax.set_ylim(-33, 33)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=100, facecolor="white")
    plt.close(fig)
    return str(path)


def main():
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
                    ("direct", dict(manifold="direct")),
                    ("top_edge_none", dict(top_edge="none")),
                    ("top_edge_chamfer", dict(top_edge="chamfer", top_edge_size=2.5))):
        q = H.RingParams(**kw); built = H.build(q)
        alt[key] = dict(params=kw, verify=H.verify(q, built), paths=H.path_lengths(q))
        if key == "top_edge_none":
            alt[key]["stl_sha256"] = hashlib.sha256(H.stl_bytes(built["ring"])).hexdigest()

    imgs = []
    edge = f"Top inner edge: {p.top_edge} {L['top_edge_size']:g} mm ({L['top_edge_profile']}, depth {L['top_edge_depth']:.2f} mm)."
    cap = f"Tilt {p.tilt_deg:g} deg DOWN, swirl {p.swirl_deg:g} deg. COLD-GAS TEST FIXTURE ONLY - never light the PLA ring."
    imgs.append(render([(ring, RING), (tips, BRASS), (jets, JET)], OUT / "iso.png", (1, -1.2, 0.9),
                       f"Iso: ring + 4 brass tips + jet lines (red)\n{cap}\n{edge}"))
    imgs.append(render([(ring, RING), (tips, BRASS), (jets, JET)], OUT / "top.png", (0, 0, 1),
                       f"Top: jets swirl CCW round a {2*J['vortex_core_radius_mm']:.1f} mm vortex core. {edge}", up=(0, 1, 0)))
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
    path_mm = next(iter(rep["path_balance"]["paths_mm"].values()))
    labeled = gas_path_labeled(p, L, OUT / "gas_path_labeled.png", paths_mm=path_mm)
    imgs.append(labeled)
    board(imgs, OUT / "hho_vortex_ring_board.png",
          "HHO vortex nozzle ring v2 (rounded 2.5 mm top inner edge) - PLA COLD-GAS TEST FIXTURE ONLY (metal STEP for the real head)",
          cols=4)
    summary = dict(params=H.params_dict(p), report=rep, verify=ver, direct_manifold_paths=rep_direct, variants=alt,
                   files=dict(stl=str(stl), step=str(step), cavity=str(OUT / "hho_vortex_ring_gas_cavity_reference.stl"),
                              images=imgs, board=str(OUT / "hho_vortex_ring_board.png"),
                              gas_path_labeled=str(OUT / "gas_path_labeled.png")),
                   tip=H.TIPS[p.tip], safety=H.SAFETY)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(dict(verify=ver, jets=J, paths=rep["path_balance"], top_edge=rep["top_edge"], direct=rep_direct,
                          variants={k: ((v["verify"] or {}).get("ok"), (v["verify"] or {}).get("size_mm")) for k, v in alt.items()}), indent=1))



if __name__ == "__main__":
    main()
