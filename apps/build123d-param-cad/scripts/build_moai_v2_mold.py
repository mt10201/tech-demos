"""Export + verify + render the Moai v2 hi-res master, integral tooling base and pour frame.

    PYOPENGL_PLATFORM=egl python3 scripts/build_moai_v2_mold.py [/workspace/exports/moai_v2]
"""
from __future__ import annotations

import hashlib, json, math, sys, zipfile
from pathlib import Path

import numpy as np
import trimesh
import manifold3d as mf

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "scripts"))
import moai_mold, moai_v2  # noqa: E402
from moai_render import render, board  # noqa: E402

_args = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = Path(_args[0]) if _args else Path("/workspace/exports/moai_v2")
ORIG = HERE / "assets/moai_head_scan_152mm.stl"
V1 = HERE / "assets/moai_head_scan_152mm_v1_blend.stl"


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def self_intersections(m: trimesh.Trimesh, cell=1.0, chunk=400_000):
    """Count pairs of non-adjacent triangles that intersect (edge-vs-triangle Moller-Trumbore on a
    uniform-grid broad phase). Exact for non-coplanar pairs; returns (pairs_tested, hits)."""
    T = m.triangles; F = m.faces
    lo = T.min(1); hi = T.max(1); o = m.bounds[0]
    a = np.floor((lo - o) / cell).astype(np.int64); b = np.floor((hi - o) / cell).astype(np.int64)
    dims = b.max(0) + 2
    tri, key = [], []
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                c = a + [dx, dy, dz]
                ok = np.all(c <= b, 1)
                idx = np.where(ok)[0]
                tri.append(idx); key.append(np.ravel_multi_index(c[ok].T, dims))
    tri = np.concatenate(tri); key = np.concatenate(key)
    srt = np.argsort(key, kind="stable"); tri = tri[srt]; key = key[srt]
    starts = np.r_[0, np.where(np.diff(key))[0] + 1]; counts = np.diff(np.r_[starts, len(key)])
    pairs = []
    for n in range(2, counts.max() + 1):
        s = starts[counts == n]
        if not len(s): continue
        g = tri[s[:, None] + np.arange(n)]
        i, j = np.triu_indices(n, 1)
        pairs.append(np.c_[g[:, i].ravel(), g[:, j].ravel()])
    P = np.unique(np.sort(np.concatenate(pairs), 1), axis=0)
    share = (F[P[:, 0]][:, :, None] == F[P[:, 1]][:, None, :]).any((1, 2))
    P = P[~share]
    bl = np.all((lo[P[:, 0]] <= hi[P[:, 1]]) & (lo[P[:, 1]] <= hi[P[:, 0]]), 1)
    P = P[bl]
    hits = 0
    def seg_tri(p0, p1, t):
        e1 = t[:, 1] - t[:, 0]; e2 = t[:, 2] - t[:, 0]; d = p1 - p0
        h = np.cross(d, e2); aa = np.einsum("ij,ij->i", e1, h)
        ok = np.abs(aa) > 1e-12; f = np.where(ok, 1 / np.where(ok, aa, 1), 0)
        s = p0 - t[:, 0]; u = f * np.einsum("ij,ij->i", s, h)
        q = np.cross(s, e1); v = f * np.einsum("ij,ij->i", d, q); tt = f * np.einsum("ij,ij->i", e2, q)
        eps = 1e-9
        return ok & (u > eps) & (v > eps) & (u + v < 1 - eps) & (tt > eps) & (tt < 1 - eps)
    for k in range(0, len(P), chunk):
        p = P[k:k + chunk]; A = T[p[:, 0]]; B = T[p[:, 1]]
        hit = np.zeros(len(p), bool)
        for X, Y in ((A, B), (B, A)):
            for e in ((0, 1), (1, 2), (2, 0)):
                hit |= seg_tri(X[:, e[0]], X[:, e[1]], Y)
        hits += int(hit.sum())
    return int(len(P)), hits


def check(m: trimesh.Trimesh, name: str, si=True) -> dict:
    man = mf.Manifold(mf.Mesh(m.vertices.astype(np.float32), m.faces.astype(np.uint32)))
    rt = man.to_mesh()
    r = dict(file=name, triangles=int(len(m.faces)), watertight=bool(m.is_watertight),
             winding_consistent=bool(m.is_winding_consistent), is_volume=bool(m.is_volume),
             euler=int(m.euler_number), genus=int((2 - m.euler_number) // 2),
             bodies=len(m.split(only_watertight=False)), volume_ml=round(float(m.volume) / 1000, 3),
             extents_mm=[round(float(x), 2) for x in m.extents], min_z=round(float(m.bounds[0][2]), 4),
             manifold3d_status=str(man.status()), manifold3d_genus=int(man.genus()),
             manifold3d_volume_ml=round(float(man.volume()) / 1000, 3),
             manifold3d_roundtrip_tris=int(len(np.asarray(rt.tri_verts))))
    if si:
        tested, hits = self_intersections(m)
        r.update(self_intersection_pairs_tested=tested, self_intersecting_pairs=hits)
    return r


def make_zips(paths):
    """Chat zips (each < 25 MB): print set (master + frame + docs + boards) and the statue alone."""
    docs = [OUT / "verification.json", OUT / "ATTRIBUTION.md", OUT / "README.md"]
    sets = {"moai_v2_PRINT_SET_master_frame.zip": [paths["master"], paths["pour_frame"], *docs, *sorted(OUT.glob("board_*.png"))],
            "moai_v2_statue_only.zip": [paths["statue"], OUT / "ATTRIBUTION.md", OUT / "README.md"]}
    for zn, files in sets.items():
        z = OUT / zn
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for p in files:
                if p.is_file(): zf.write(p, p.name)
        print("zip", z, z.stat().st_size)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if "--zip-only" in sys.argv:
        return make_zips({k: OUT / n for k, n in moai_v2.FILES.items()})
    st = moai_v2.statue()
    parts = moai_v2.parts(); d = moai_v2.dims()
    meshes = {"statue": st}
    for k in ("master", "pour_frame"):
        v, f = parts[k]; meshes[k] = trimesh.Trimesh(v, f, process=True)
    paths = {}
    for k, m in meshes.items():
        p = OUT / moai_v2.FILES[k]
        if k == "statue": p.write_bytes(moai_v2.STATUE_STL.read_bytes())
        else: m.export(p)
        paths[k] = p
    ver = {k: check(meshes[k], moai_v2.FILES[k]) for k in meshes}
    for k in ver: ver[k]["bytes"] = paths[k].stat().st_size; ver[k]["sha256"] = sha(paths[k])
    # exact silicone: faceted cavity above plate (z 0..fill) minus statue sunk 0.5 mm, clipped at z>=0
    ri = d.frame_id / 2
    cav = mf.Manifold.cylinder(d.fill_above_plate_mm, ri, ri, moai_mold.SEG)
    sv = st.vertices.copy(); sv[:, 2] -= moai_mold.STATUE_SINK
    sman = mf.Manifold(mf.Mesh(sv.astype(np.float32), st.faces.astype(np.uint32)))
    exposed = sman ^ mf.Manifold.cube((400, 400, 400), True).translate((0, 0, 200))
    cav_ml = cav.volume() / 1000; st_ml = exposed.volume() / 1000
    rr = np.sqrt((st.vertices[:, :2] ** 2).sum(1))
    apothem = ri * math.cos(math.pi / moai_mold.SEG)
    sil = dict(cavity_ml=round(cav_ml, 3), exposed_statue_ml=round(st_ml, 3), silicone_ml=round(cav_ml - st_ml, 1),
               min_side_silicone_mm_faceted=round(apothem - float(rr.max()), 3),
               top_cover_mm=round(d.top_cover_mm, 2), fill_above_plate_mm=round(d.fill_above_plate_mm, 2),
               note="mixed volume only; cup/mixing loss, leaks and reserve excluded")
    dd = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in d.__dict__.items()}
    # face preservation vs original (same scan, finer voxel): distance of original face verts to v2 surface
    o = trimesh.load(ORIG, process=True)
    face = (o.vertices[:, 1] < -1.0) & (np.abs(o.vertices[:, 0]) < 18) & (o.vertices[:, 2] > 20) & (o.vertices[:, 2] < 145)
    _, dist, _ = trimesh.proximity.closest_point(st, o.vertices[face][::4])
    facecmp = dict(n=int(len(dist)), median_mm=round(float(np.median(dist)), 3), p99_mm=round(float(np.percentile(dist, 99)), 3),
                   max_mm=round(float(dist.max()), 3))
    rep = dict(original_sha256=sha(ORIG), original_unchanged=sha(ORIG) == "f2c214d8b9b32f2502e5f73ba2bfe0563575c28f25a9a0ee2cd065e2ecd8494a",
               dims=dd, silicone=sil, parts=ver, face_vs_original=facecmp,
               ender2_check=dict(master_xy_mm=ver["master"]["extents_mm"][:2], master_h=ver["master"]["extents_mm"][2],
                                 frame=ver["pour_frame"]["extents_mm"], limit="150 x 150 x 200 (conservative)"))
    (OUT / "verification.json").write_text(json.dumps(rep, indent=2))
    print(json.dumps({k: rep[k] for k in ("silicone", "face_vs_original", "ender2_check")}, indent=1))
    for k, r in ver.items(): print(k, {x: r[x] for x in ("triangles", "watertight", "euler", "genus", "bodies", "volume_ml", "extents_mm", "self_intersecting_pairs", "bytes")})
    # ---- renders (opaque, full surface, identical cameras for original and v2) ----
    R = OUT / "renders"; R.mkdir(exist_ok=True)
    orig = o; v1 = trimesh.load(V1, process=True)
    views = {"front": (0, -1, 0.08), "side_statue_left": (1, 0, 0.08), "side_statue_right": (-1, 0, 0.08),
             "back": (0, 1, 0.12), "top": (0.01, 0.25, 1), "three_quarter": (0.75, -0.7, 0.25), "rear_three_quarter": (0.8, 0.65, 0.3)}
    full = []
    for name, dv in views.items():
        for tag, m in (("original", orig), ("v2", st)):
            full.append(render(m, R / f"{tag}_{name}.png", dv, target=(0, 0, 76), mag=82, size=(520, 640), title=f"{tag.upper()} {name}", smooth=True))
    board(full[:8], OUT / "board_front_sides_back.png", "ORIGINAL (left of each pair) vs MOAI V2 (right) - same cameras, opaque", cols=4)
    board(full[8:], OUT / "board_top_3q.png", "ORIGINAL vs MOAI V2 - top, 3/4, rear 3/4", cols=6)
    close = {"ear_statue_left_side": ((1, 0.25, 0.1), (25, 15, 95), 60), "ear_statue_right_side": ((-1, 0.25, 0.1), (-25, 15, 95), 60),
             "ear_statue_left_rear_oblique": ((1, 0.6, 0.1), (25, 15, 100), 40), "ear_statue_right_rear_oblique": ((-1, 0.6, 0.1), (-25, 15, 100), 40),
             "crown_top_back": ((0.2, 0.9, 1.0), (0, 12, 140), 34), "eyes_front": ((0, -1, 0.05), (0, -10, 115), 26)}
    cl = []
    for name, (dv, tg, mg) in close.items():
        for tag, m in (("original", orig), ("v1", v1), ("v2", st)):
            cl.append(render(m, R / f"{tag}_{name}.png", dv, target=tg, mag=mg, size=(480, 600), title=f"{tag.upper()} {name}", smooth=True))
    board(cl[:6], OUT / "board_ears_side.png", "Ears, side view: ORIGINAL | V1 | V2 (statue-left, then statue-right)", cols=6)
    board(cl[6:12], OUT / "board_ears_rear_oblique.png", "Ear/head join, rear-oblique: ORIGINAL | V1 | V2", cols=6)
    board(cl[12:], OUT / "board_crown_eyes.png", "Crown (top-back) and eyes: ORIGINAL | V1 | V2", cols=6)
    # assembly: master + seated frame with the front half of the frame cut away for visibility (render only)
    mst = meshes["master"].copy(); mst.apply_translation((0, 0, -moai_mold.PLATE_T))
    frm = meshes["pour_frame"].copy(); frm.apply_translation((0, 0, -moai_mold.GR_DEPTH))
    half = trimesh.intersections.slice_mesh_plane(frm, (0, 1, 0), (0, 0, 0), cap=True)
    asm = trimesh.util.concatenate([mst, half])
    a1 = render(asm, R / "assembly_cutaway.png", (0.15, -1, 0.35), target=(0, 0, 75), mag=95, size=(640, 720), title="Master + seated frame (front half of frame hidden in render only)", smooth=True)
    a2 = render(trimesh.util.concatenate([mst, frm]), R / "assembly_closed.png", (0.6, -0.8, 0.5), target=(0, 0, 75), mag=95, size=(640, 720), title="Master + frame, closed", smooth=True)
    a3 = render(mst, R / "master_with_base.png", (0.6, -0.8, 0.35), target=(0, 0, 75), mag=90, size=(640, 720), title="V2 master with integral base", smooth=True)
    lipc = render(asm, R / "lip_channel_closeup.png", (0.05, -1, 0.15), target=(d.frame_gr_out - 4, 0, 0), mag=9, size=(640, 520), title="Groove / glue channel / outer lip (section)", smooth=False)
    board([a3, a1, a2], OUT / "board_mold_assembly.png", "Moai v2 mold tooling (tower v3 seating, 0.25 mm/side)", cols=3)
    make_zips(paths)

if __name__ == "__main__":
    main()
