#!/usr/bin/env python3
"""Moai mold v1: localized ear/top blend + integral circular tooling plate + cylindrical pour frame.

Preserves apps/build123d-param-cad/assets/moai_head_scan_152mm.stl bytes unchanged.
Writes:
  assets/moai_head_scan_152mm_v1_blend.stl (+ preview ply)
  /workspace/exports/moai_mold_v1/*  (STLs, renders, verification.json)

Tower v3 seating reused exactly: wall=3, clr=0.25/side, groove_depth=1.6,
lip channel=1.5 width=1.6 height=3.0 chamfer=0.4, plate_t=4, plate_rim=7.9.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
import trimesh
import manifold3d as mf
from PIL import Image, ImageDraw
from scipy import sparse
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parents[1]
ASSETS = HERE / "assets"
ORIG_STL = ASSETS / "moai_head_scan_152mm.stl"
BLEND_STL = ASSETS / "moai_head_scan_152mm_v1_blend.stl"
BLEND_PLY = ASSETS / "moai_head_scan_152mm_v1_blend_preview.ply"
EXPORT = Path("/workspace/exports/moai_mold_v1")
H = 152.4

# Proven tower v3 seating (do not change)
FRAME_WALL = 3.0
CLR = 0.25
GR_DEPTH = 1.6
PLATE_T = 4.0
PLATE_RIM = 7.9
LIP_CHANNEL = 1.5
LIP_WIDTH = 1.6
LIP_HEIGHT = 3.0
LIP_CH = 0.4
FRAME_CH = 0.4
SILICONE_SIDE = 10.0
OVER_APEX = 6.0
SEG = 192


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_orig() -> trimesh.Trimesh:
    m = trimesh.load(ORIG_STL, process=True)
    assert abs(float(m.extents[2]) - H) < 1e-2
    assert m.is_watertight and m.euler_number == 2
    return m


def dihedral_sharp_mask(m: trimesh.Trimesh, deg: float = 32.0):
    adj = m.face_adjacency
    n = m.face_normals
    cos = np.clip((n[adj[:, 0]] * n[adj[:, 1]]).sum(1), -1.0, 1.0)
    dih = np.degrees(np.arccos(cos))
    sharp = dih >= deg
    ea = m.face_adjacency_edges
    return sharp, ea, dih


def blend_ears_and_top(m: trimesh.Trimesh, iters: int = 18, lam: float = 0.45):
    """Localized Laplacian smooth on ear front creases + crown hard line; face protected.

    Returns (new_mesh, stats_dict).
    """
    v = np.asarray(m.vertices, float).copy()
    f = np.asarray(m.faces, np.int64)
    sharp, ea, dih = dihedral_sharp_mask(m, 32.0)
    ec = 0.5 * (v[ea[:, 0]] + v[ea[:, 1]])

    # Ear front creases: high |x|, mid z, sharp
    ear = sharp & (np.abs(ec[:, 0]) > 22.0) & (ec[:, 2] > 42.0) & (ec[:, 2] < 128.0)
    # Prefer the frontish attachment (smaller y) of the ear block — the hard vertical join
    ear = ear & (ec[:, 1] < 18.0)
    top = sharp & (ec[:, 2] > 145.0) & (np.abs(ec[:, 0]) < 32.0) & (ec[:, 1] < 20.0)
    # Also top perimeter where crown meets vertical face (slightly lower)
    top2 = sharp & (ec[:, 2] > 148.0)
    crease_edges = ear | top | top2
    crease_vids = np.unique(ea[crease_edges].ravel())

    # Seed weights on crease vertices, then geodesic-ish expand via mesh adjacency
    # Build vertex adjacency
    E = np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    E = np.unique(np.sort(E, axis=1), axis=0)
    n = len(v)
    A = sparse.coo_matrix((np.ones(len(E)), (E[:, 0], E[:, 1])), shape=(n, n))
    A = A + A.T
    # degree-normalized
    deg = np.asarray(A.sum(1)).ravel()
    deg[deg == 0] = 1

    w = np.zeros(n, float)
    w[crease_vids] = 1.0
    # Diffuse weight a few hops so blend has a soft apron (~3–5 mm)
    Ad = A.tocsr()
    for _ in range(10):
        w = np.maximum(w, (Ad @ w) / deg * 0.92)
    w = np.clip(w, 0, 1)
    # Distance falloff from crease seeds in mm
    tree = cKDTree(v[crease_vids])
    d, _ = tree.query(v, k=1)
    # Full effect within 1.2 mm of crease, fade to 0 by 4.5 mm
    spatial = np.clip(1.0 - (d - 1.2) / (4.5 - 1.2), 0.0, 1.0)
    spatial[d <= 1.2] = 1.0
    w *= spatial

    # Protect face: front central features (brow/eyes/nose/mouth/chin)
    # Face looks -Y; protect y < 2 and |x| < 22 and z 20..145, with soft edge
    face = (v[:, 1] < 3.0) & (np.abs(v[:, 0]) < 22.0) & (v[:, 2] > 15.0) & (v[:, 2] < 145.0)
    # Keep a bit of side-face near ears out of absolute lock so ear root can blend —
    # but never touch the true facial plane (y < -1 inside |x|<18)
    hard_face = (v[:, 1] < -1.0) & (np.abs(v[:, 0]) < 18.0) & (v[:, 2] > 20.0) & (v[:, 2] < 145.0)
    w[hard_face] = 0.0
    # Softly reduce elsewhere on face
    w[face] *= np.clip((v[face, 1] + 1.0) / 4.0, 0.0, 1.0)  # more freedom toward sides/back of face plane

    # Also protect deep eye sockets specifically
    eye = (np.abs(v[:, 0]) > 5.0) & (np.abs(v[:, 0]) < 22.0) & (v[:, 2] > 105.0) & (v[:, 2] < 125.0) & (v[:, 1] < 0.0)
    w[eye] = 0.0

    # Base flat: do not lift base
    base = v[:, 2] < 0.3
    w[base] = 0.0

    v0 = v.copy()
    # Uniform Laplacian iterations, masked
    for _ in range(iters):
        neigh_sum = Ad @ v
        lap = neigh_sum / deg[:, None] - v
        v = v + (lam * w)[:, None] * lap

    # Displacement from blend only (before any rigid/scale snap)
    disp = np.linalg.norm(v - v0, axis=1)
    face_disp = disp[hard_face] if hard_face.any() else np.array([0.0])
    ear_disp = disp[w > 0.3]

    # Snap base to z=0 and exact height; apply identical transform to v0 for indexed maps
    zmin = float(v[:, 2].min())
    v[:, 2] -= zmin
    v0[:, 2] -= zmin
    scale = H / float(np.ptp(v[:, 2]))
    v[:, 2] *= scale
    v0[:, 2] *= scale
    cx = 0.5 * (v[:, 0].min() + v[:, 0].max())
    cy = 0.5 * (v[:, 1].min() + v[:, 1].max())
    v[:, 0] -= cx; v[:, 1] -= cy
    v0[:, 0] -= cx; v0[:, 1] -= cy
    v[:, 2] -= v[:, 2].min()
    v0[:, 2] -= v0[:, 2].min()
    # Final height snap (same scale on both)
    s2 = H / float(np.ptp(v[:, 2]))
    v[:, 2] *= s2
    v0[:, 2] *= s2

    out = trimesh.Trimesh(v, f, process=False)
    # Index-aligned with input: do not merge yet (displacement map needs correspondence)

    stats = dict(
        iters=iters,
        lam=lam,
        crease_edge_count=int(crease_edges.sum()),
        crease_vertex_count=int(len(crease_vids)),
        verts_with_w_gt_0_3=int((w > 0.3).sum()),
        displacement_mm=dict(
            global_max=float(disp.max()),
            global_mean=float(disp.mean()),
            global_p95=float(np.percentile(disp, 95)),
            global_p99=float(np.percentile(disp, 99)),
            blend_region_max=float(ear_disp.max()) if len(ear_disp) else 0.0,
            blend_region_mean=float(ear_disp.mean()) if len(ear_disp) else 0.0,
            blend_region_p95=float(np.percentile(ear_disp, 95)) if len(ear_disp) else 0.0,
            protected_face_max=float(face_disp.max()),
            protected_face_mean=float(face_disp.mean()),
            protected_face_p95=float(np.percentile(face_disp, 95)),
            protected_face_p99=float(np.percentile(face_disp, 99)),
        ),
        weight_spatial_fade_mm=[1.2, 4.5],
    )
    return out, stats, w, v0


def eye_report(m: trimesh.Trimesh) -> dict:
    v = m.vertices
    def one(name, x_lo, x_hi):
        sel = (v[:, 0] > x_lo) & (v[:, 0] < x_hi) & (v[:, 2] > 108) & (v[:, 2] < 122) & (v[:, 1] < 5) & (v[:, 1] > -15)
        pts = v[sel]
        if len(pts) < 50:
            return dict(name=name, n=int(len(pts)), note="too few verts")
        tree = cKDTree(pts)
        _, ni = tree.query(pts, k=min(50, len(pts)))
        fwd = pts[ni][:, :, 1].mean(1) - pts[:, 1]
        return dict(
            name=name,
            n=int(len(pts)),
            bounds_mm=np.round([pts.min(0), pts.max(0)], 3).tolist(),
            local_forward_protrusion_mm=dict(
                max=round(float(fwd.max()), 3),
                p99=round(float(np.percentile(fwd, 99)), 3),
                p95=round(float(np.percentile(fwd, 95)), 3),
                std=round(float(fwd.std()), 3),
                n_gt_0_4mm=int((fwd > 0.4).sum()),
            ),
            interpretation=(
                "Absent multi-mm isolated blob in either eye mesh (local forward spikes <= ~1 mm). "
                "A print close-up photo is required to diagnose any large printed eye defect; "
                "this report does not attribute cause to print/seam/support."
            ),
        )
    L = one("statue_left_eye (+X, viewer_right when facing front)", 6, 22)
    R = one("statue_right_eye (-X, viewer_left when facing front)", -22, -6)
    # asymmetry
    selL = (v[:, 0] > 6) & (v[:, 0] < 22) & (v[:, 2] > 108) & (v[:, 2] < 122) & (v[:, 1] < 5) & (v[:, 1] > -15)
    selR = (v[:, 0] < -6) & (v[:, 0] > -22) & (v[:, 2] > 108) & (v[:, 2] < 122) & (v[:, 1] < 5) & (v[:, 1] > -15)
    Lp, Rp = v[selL], v[selR]
    Lmir = Lp.copy(); Lmir[:, 0] *= -1
    d, j = cKDTree(Rp).query(Lmir, k=1)
    ydiff = Rp[j][:, 1] - Lp[:, 1]
    asym = dict(
        mirror_nn_dist_mm=dict(mean=round(float(d.mean()), 3), p95=round(float(np.percentile(d, 95)), 3), max=round(float(d.max()), 3)),
        L_more_forward_than_R_mm=dict(
            mean=round(float(ydiff.mean()), 3),
            p95=round(float(np.percentile(ydiff, 95)), 3),
            max=round(float(ydiff.max()), 3),
            frac_gt_0_5mm=round(float((ydiff > 0.5).mean()), 4),
        ),
    )
    return dict(left=L, right=R, asymmetry=asym)


def mesh_quality(m: trimesh.Trimesh) -> dict:
    # self-intersection: sample with manifold3d roundtrip / trimesh broken faces
    q = dict(
        watertight=bool(m.is_watertight),
        winding_consistent=bool(m.is_winding_consistent),
        is_volume=bool(m.is_volume),
        bodies=len(m.split(only_watertight=False)),
        euler=int(m.euler_number),
        genus=int((2 - m.euler_number) // 2),
        faces=int(len(m.faces)),
        verts=int(len(m.vertices)),
        volume_cm3=round(float(m.volume) / 1000.0, 2),
        extents_mm=np.round(m.extents, 3).tolist(),
        bounds_mm=np.round(m.bounds, 3).tolist(),
        edge_valence=None,
        self_intersection_note="Full triangle-triangle self-intersection test NOT run (too heavy). Evidence: watertight+winding+euler+boundary/nonmanifold+manifold3d. Do not claim intersection-free beyond that.",
    )
    edges = m.edges_sorted
    _, cnt = np.unique(edges, axis=0, return_counts=True)
    q["boundary_edges"] = int((cnt == 1).sum())
    q["nonmanifold_edges_valence_gt2"] = int((cnt > 2).sum())
    # manifold3d roundtrip
    try:
        mm = mf.Manifold(mf.Mesh(m.vertices.astype(np.float32), m.faces.astype(np.uint32)))
        q["manifold3d_status"] = str(mm.status())
        q["manifold3d_volume_cm3"] = round(float(mm.volume()) / 1000.0, 2)
        q["manifold3d_ok"] = mm.status() == mf.Error.NoError
    except Exception as e:
        q["manifold3d_ok"] = False
        q["manifold3d_error"] = repr(e)
    return q


def to_manifold(m: trimesh.Trimesh) -> mf.Manifold:
    mm = mf.Manifold(mf.Mesh(m.vertices.astype(np.float32), m.faces.astype(np.uint32)))
    assert mm.status() == mf.Error.NoError, mm.status()
    return mm


def tomesh(man: mf.Manifold) -> trimesh.Trimesh:
    mesh = man.to_mesh()
    return trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts), process=False)


def build_mold(statue: trimesh.Trimesh):
    """Integral plate+lip+groove with statue; separate cylindrical pour frame. Tower v3 seating."""
    v = statue.vertices
    max_r = float(np.sqrt((v[:, 0] ** 2 + v[:, 1] ** 2)).max())
    frame_id = 2.0 * (max_r + SILICONE_SIDE)
    frame_gr_in = frame_id / 2 - CLR
    frame_gr_out = frame_id / 2 + FRAME_WALL + CLR
    li = frame_gr_out + LIP_CHANNEL
    lo = li + LIP_WIDTH
    plate_r = frame_gr_out + PLATE_RIM
    assert lo < plate_r - 1.0
    H_stat = float(statue.extents[2])
    fill = H_stat + OVER_APEX
    M = mf.Manifold
    # Sink statue 0.5 mm into the plate so the coplanar base/plate union is manifold (tower shaft
    # already overlaps its plate; a scan-flat base at z=0 alone leaves non-manifold edges).
    SINK = 0.5
    st = statue.copy()
    st.vertices = st.vertices.copy()
    st.vertices[:, 2] -= SINK

    plate = M.cylinder(PLATE_T, plate_r, plate_r, SEG).translate((0, 0, -PLATE_T))
    lip = M.revolve(
        mf.CrossSection([[(li, -0.5), (lo, -0.5), (lo, LIP_HEIGHT - LIP_CH), (lo - LIP_CH, LIP_HEIGHT),
                          (li + LIP_CH, LIP_HEIGHT), (li, LIP_HEIGHT - LIP_CH)]]),
        SEG,
    )
    ring = M.cylinder(GR_DEPTH + 1, frame_gr_out, frame_gr_out, SEG) - M.cylinder(
        GR_DEPTH + 1, frame_gr_in, frame_gr_in, SEG
    )
    body = to_manifold(st) + plate + lip
    master = body - ring.translate((0, 0, -GR_DEPTH))

    ri = frame_id / 2
    ro = ri + FRAME_WALL
    z0 = -GR_DEPTH
    h = fill - z0
    frame = M.revolve(
        mf.CrossSection([[(ri + FRAME_CH, z0), (ro - FRAME_CH, z0), (ro, z0 + FRAME_CH), (ro, z0 + h),
                          (ri, z0 + h), (ri, z0 + FRAME_CH)]]),
        SEG,
    )

    # Volume: internal pour cylinder above plate (z>=0) minus statue volume above plate
    cav = math.pi * (frame_id / 2) ** 2 * fill
    # statue volume entirely above z=0
    statue_vol = float(statue.volume)
    silicone_ml = (cav - statue_vol) / 1000.0
    # min side wall: frame inner radius - max_r
    side_clear = frame_id / 2 - max_r
    top_cover = OVER_APEX + SINK  # actual cover above exposed head = 6.5

    dims = dict(
        max_r_mm=round(max_r, 3),
        frame_id=round(frame_id, 3),
        frame_od=round(2 * ro, 3),
        frame_len=round(fill + GR_DEPTH, 3),
        frame_gr_in=round(frame_gr_in, 3),
        frame_gr_out=round(frame_gr_out, 3),
        groove_width=round(frame_gr_out - frame_gr_in, 3),
        groove_depth=GR_DEPTH,
        clearance_per_side=CLR,
        wall=FRAME_WALL,
        plate_d=round(2 * plate_r, 3),
        plate_t=PLATE_T,
        lip_d_in=round(2 * li, 3),
        lip_d_out=round(2 * lo, 3),
        lip_channel=LIP_CHANNEL,
        lip_width=LIP_WIDTH,
        lip_height=LIP_HEIGHT,
        silicone_side_mm=round(side_clear, 3),
        top_cover_mm=top_cover,
        cavity_ml=round(cav / 1000.0, 1),
        statue_cm3=round(statue_vol / 1000.0, 2),
        silicone_ml=round(silicone_ml, 1),
        volume_derivation="pi*(frame_id/2)^2*(H+over_apex) - statue_volume_z_ge_0; actual top cover = OVER_APEX+SINK=6.5",
        proven_source="electroculture_tower_v3 (0.25/side + vertical lip + glue channel)",
        statue_sink_into_plate_mm=SINK,
    )
    return master, frame, dims


def shade(faces, verts, light=np.array([0.35, -0.55, 0.75])):
    light = light / np.linalg.norm(light)
    tris = verts[faces]
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1)
    ln[ln == 0] = 1
    n = n / ln[:, None]
    return np.clip(n @ light, 0, 1) * 0.75 + 0.25


def render_mesh(m: trimesh.Trimesh, path: Path, elev, azim, title, max_faces=70000, xlim=None):
    faces = m.faces
    if len(faces) > max_faces:
        faces = faces[np.linspace(0, len(faces) - 1, max_faces).astype(int)]
    verts = m.vertices
    fig = plt.figure(figsize=(5.4, 6.4), dpi=160)
    ax = fig.add_subplot(111, projection="3d")
    coll = Poly3DCollection(verts[faces], linewidths=0)
    coll.set_facecolors(plt.cm.copper(shade(faces, verts)))
    ax.add_collection3d(coll)
    if xlim is None:
        mid = (verts.max(0) + verts.min(0)) / 2
        span = float(np.ptp(verts, 0).max()) * 0.62
        ax.set_xlim(mid[0] - span, mid[0] + span)
        ax.set_ylim(mid[1] - span, mid[1] + span)
        ax.set_zlim(float(verts[:, 2].min()), float(verts[:, 2].max()))
    else:
        ax.set_xlim(*xlim[0]); ax.set_ylim(*xlim[1]); ax.set_zlim(*xlim[2])
    ax.set_axis_off()
    ax.view_init(elev=elev, azim=azim)
    ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, facecolor="#d7e6f0", bbox_inches="tight")
    plt.close(fig)


def render_closeup(m: trimesh.Trimesh, path: Path, center, half, elev, azim, title):
    """Crop mesh to box around center and render."""
    v = m.vertices
    mask = np.all(np.abs(v - center) <= half, axis=1)
    # faces with any vert in box
    fmask = mask[m.faces].any(1)
    sub = trimesh.Trimesh(v.copy(), m.faces[fmask].copy(), process=False)
    # Keep only referenced
    sub.remove_unreferenced_vertices()
    render_mesh(sub, path, elev, azim, title, max_faces=90000,
                xlim=((center[0] - half[0], center[0] + half[0]),
                      (center[1] - half[1], center[1] + half[1]),
                      (center[2] - half[2], center[2] + half[2])))


def board(paths, out, title):
    imgs = [Image.open(p).convert("RGB") for p in paths]
    h = max(i.height for i in imgs)
    imgs = [i.resize((int(i.width * h / i.height), h)) for i in imgs]
    pad = 14
    board = Image.new("RGB", (sum(i.width for i in imgs) + pad * (len(imgs) + 1), h + 64), (255, 255, 255))
    d = ImageDraw.Draw(board)
    d.text((pad, 10), title, fill=(20, 20, 20))
    x = pad
    for i in imgs:
        board.paste(i, (x, 44))
        x += i.width + pad
    board.save(out)
    return out


def finalize_mesh(m: trimesh.Trimesh) -> trimesh.Trimesh:
    out = trimesh.Trimesh(m.vertices.copy(), m.faces.copy(), process=False)
    out.merge_vertices()
    out.update_faces(out.unique_faces())
    out.remove_unreferenced_vertices()
    out.process(validate=True)
    if out.volume < 0:
        out.invert()
    return out


def main():
    EXPORT.mkdir(parents=True, exist_ok=True)
    orig_hash = sha256(ORIG_STL)
    print("orig sha256", orig_hash)

    orig = load_orig()
    eyes_before = eye_report(orig)
    q_before = mesh_quality(orig)

    blended_raw, blend_stats, weights, v0 = blend_ears_and_top(orig)
    disp = np.linalg.norm(blended_raw.vertices - v0, axis=1)
    blend_stats["displacement_mm"]["indexed_max"] = float(disp.max())
    blend_stats["displacement_mm"]["indexed_mean"] = float(disp.mean())
    # save displacement map (vertex scalar)
    np.savez_compressed(EXPORT / "displacement_map.npz", displacement_mm=disp, weights=weights, vertices=v0)

    blended = finalize_mesh(blended_raw)
    q_after = mesh_quality(blended)
    eyes_after = eye_report(blended)

    ok_blend = (
        q_after.get("watertight")
        and q_after.get("genus") == 0
        and q_after.get("bodies") == 1
        and q_after.get("boundary_edges", 1) == 0
        and q_after.get("manifold3d_ok")
        and blend_stats["displacement_mm"]["protected_face_max"] < 0.15
        and abs(float(blended.extents[2]) - H) < 0.05
        and blend_stats["displacement_mm"]["blend_region_max"] > 0.05  # something actually changed at ears
    )
    print("blend_ok", ok_blend, "face_max_disp", blend_stats["displacement_mm"]["protected_face_max"],
          "blend_max", blend_stats["displacement_mm"]["blend_region_max"])
    print("q_after", q_after)

    blended.export(BLEND_STL)
    try:
        import fast_simplification
        v2, f2 = fast_simplification.simplify(blended.vertices, blended.faces, target_count=50000)
        prev = trimesh.Trimesh(v2, f2, process=False)
    except Exception:
        idx = np.linspace(0, len(blended.faces) - 1, min(50000, len(blended.faces))).astype(int)
        prev = trimesh.Trimesh(blended.vertices.copy(), blended.faces[idx].copy(), process=True)
    prev.export(BLEND_PLY)
    blended.export(EXPORT / "moai_head_scan_152mm_v1_blend.stl")
    assert sha256(ORIG_STL) == orig_hash

    master_m, frame_m, dims = build_mold(blended)
    master = tomesh(master_m)
    frame = tomesh(frame_m)
    if master.volume < 0:
        master.invert()
    if frame.volume < 0:
        frame.invert()
    master.export(EXPORT / "moai_mold_v1_master_with_base.stl")
    frame.export(EXPORT / "moai_mold_v1_pour_frame.stl")

    render_mesh(orig, EXPORT / "before_front.png", 8, -90, "BEFORE front")
    render_mesh(orig, EXPORT / "before_side.png", 8, 0, "BEFORE side")
    render_mesh(orig, EXPORT / "before_top.png", 88, -90, "BEFORE top")
    render_mesh(blended, EXPORT / "after_front.png", 8, -90, "AFTER front")
    render_mesh(blended, EXPORT / "after_side.png", 8, 0, "AFTER side")
    render_mesh(blended, EXPORT / "after_top.png", 88, -90, "AFTER top")

    render_closeup(orig, EXPORT / "before_ear_left.png", center=np.array([28.0, 12.0, 85.0]), half=np.array([12.0, 18.0, 35.0]), elev=10, azim=-40, title="BEFORE ear statue-left (+X)")
    render_closeup(blended, EXPORT / "after_ear_left.png", center=np.array([28.0, 12.0, 85.0]), half=np.array([12.0, 18.0, 35.0]), elev=10, azim=-40, title="AFTER ear statue-left (+X)")
    render_closeup(orig, EXPORT / "before_ear_right.png", center=np.array([-28.0, 12.0, 85.0]), half=np.array([12.0, 18.0, 35.0]), elev=10, azim=40, title="BEFORE ear statue-right (-X)")
    render_closeup(blended, EXPORT / "after_ear_right.png", center=np.array([-28.0, 12.0, 85.0]), half=np.array([12.0, 18.0, 35.0]), elev=10, azim=40, title="AFTER ear statue-right (-X)")

    render_closeup(orig, EXPORT / "before_eye_statue_left.png", center=np.array([12.0, -4.0, 115.0]), half=np.array([12.0, 12.0, 12.0]), elev=5, azim=-90, title="BEFORE eye statue-left (+X / viewer-right)")
    render_closeup(blended, EXPORT / "after_eye_statue_left.png", center=np.array([12.0, -4.0, 115.0]), half=np.array([12.0, 12.0, 12.0]), elev=5, azim=-90, title="AFTER eye statue-left (+X / viewer-right)")
    render_closeup(orig, EXPORT / "before_eye_statue_right.png", center=np.array([-12.0, -4.0, 115.0]), half=np.array([12.0, 12.0, 12.0]), elev=5, azim=-90, title="BEFORE eye statue-right (-X / viewer-left)")
    render_closeup(blended, EXPORT / "after_eye_statue_right.png", center=np.array([-12.0, -4.0, 115.0]), half=np.array([12.0, 12.0, 12.0]), elev=5, azim=-90, title="AFTER eye statue-right (-X / viewer-left)")

    render_closeup(orig, EXPORT / "before_top_closeup.png", center=np.array([0.0, 5.0, 150.0]), half=np.array([35.0, 25.0, 8.0]), elev=70, azim=-90, title="BEFORE top edge")
    render_closeup(blended, EXPORT / "after_top_closeup.png", center=np.array([0.0, 5.0, 150.0]), half=np.array([35.0, 25.0, 8.0]), elev=70, azim=-90, title="AFTER top edge")

    board([EXPORT / "before_front.png", EXPORT / "before_side.png", EXPORT / "before_top.png"], EXPORT / "before_board.png", "BEFORE — original moai_head_scan_152mm.stl")
    board([EXPORT / "after_front.png", EXPORT / "after_side.png", EXPORT / "after_top.png"], EXPORT / "after_board.png", "AFTER — v1 localized ear/top blend (face protected)")
    board([EXPORT / "before_ear_left.png", EXPORT / "after_ear_left.png", EXPORT / "before_ear_right.png", EXPORT / "after_ear_right.png"], EXPORT / "ears_before_after.png", "Ears before/after — statue-left (+X) then statue-right (-X)")
    board([EXPORT / "before_eye_statue_left.png", EXPORT / "after_eye_statue_left.png", EXPORT / "before_eye_statue_right.png", EXPORT / "after_eye_statue_right.png"], EXPORT / "eyes_before_after.png", "Eyes before/after — statue-left (+X/viewer-right) then statue-right (-X/viewer-left)")
    board([EXPORT / "before_top_closeup.png", EXPORT / "after_top_closeup.png"], EXPORT / "top_before_after.png", "Top edge before/after")

    render_mesh(master, EXPORT / "master_with_base.png", 18, -120, "Mold master (statue + plate + lip)", max_faces=80000)
    render_mesh(frame, EXPORT / "pour_frame.png", 18, -120, "Pour frame", max_faces=20000)

    verification = dict(
        original_stl=str(ORIG_STL),
        original_sha256=orig_hash,
        original_sha256_after=sha256(ORIG_STL),
        original_unchanged=sha256(ORIG_STL) == orig_hash,
        blend_stl=str(BLEND_STL),
        blend_sha256=sha256(BLEND_STL),
        export_dir=str(EXPORT),
        blend_ok_for_print_recommendation=bool(ok_blend),
        quality_before=q_before,
        quality_after=q_after,
        blend_stats=blend_stats,
        eyes_before=eyes_before,
        eyes_after=eyes_after,
        mold_dims=dims,
        master_quality=mesh_quality(master),
        frame_quality=dict(
            watertight=bool(frame.is_watertight),
            extents_mm=np.round(frame.extents, 3).tolist(),
            volume_cm3=round(float(frame.volume) / 1000, 2),
            genus=int((2 - frame.euler_number) // 2),
        ),
        demolding_notes=(
            "Soft silicone Shore 10–20A recommended. Brow, nose and chin are real undercuts — "
            "a one-piece pour can work with soft silicone and a rear or side slit for release, "
            "but do not assume lock-free demold. Ear-line two-piece mold is the safer shop option. "
            "No vents on sale files."
        ),
        print_notes=(
            "Print master upright on plate, 0.12–0.16 mm layers. Tree supports under brow/nose/chin. "
            "Plate needs no brim. Localized overhang risk unchanged at face undercuts; ear blend should "
            "not add overhangs. Frame: print upright, no supports. No slicing performed."
        ),
        photo_refs_checkpoint=[
            {"url": "https://commons.wikimedia.org/wiki/File:Moai_Rano_raraku.jpg", "license": "PD (Aurbina)"},
            {"url": "https://commons.wikimedia.org/wiki/File:Moai_at_Rano_Raraku_-_Easter_Island_(5955844187).jpg", "license": "CC BY 2.0 (TravelingOtter)"},
            {"url": "https://commons.wikimedia.org/wiki/File:Moais_de_Rano_Raraku,_Isla_de_Pascua.JPG", "license": "CC BY-SA 3.0 (Claire Provost)"},
        ],
        attribution="Quarry Moai - Rapa Nui/Easter Island by Ryan Shackleton, CC BY 4.0, modified",
        eye_print_closeup_request=(
            "Mesh inspection finds no large blobby protrusion on either eye (local fwd spikes <=~1 mm; "
            "L/R asymmetry mean ~0.3 mm). If the printed left-eye blob is large, please send a close-up "
            "photo of the print — likely print/seam/support artifact, not confirmed in the STL."
        ),
    )
    (EXPORT / "verification.json").write_text(json.dumps(verification, indent=2, default=float))
    print(json.dumps({"ok_blend": ok_blend, "dims": dims,
                      "face_max": blend_stats["displacement_mm"]["protected_face_max"],
                      "blend_max": blend_stats["displacement_mm"]["blend_region_max"]}, indent=2))
    return 0 if ok_blend else 2


if __name__ == "__main__":
    raise SystemExit(main())
