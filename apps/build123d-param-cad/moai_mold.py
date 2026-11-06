"""Moai silicone mold tooling: integral circular plate + cylindrical pour frame.

Reuses the successful electroculture tower v3 seating geometry exactly:
frame wall 3.0 mm, clearance 0.25 mm per side, groove depth 1.6 mm,
vertical outer sealing lip with 1.5 mm glue-bead channel, lip 1.6×3.0 mm,
bottom chamfers 0.4 mm. Statue is sunk 0.5 mm into the plate for a manifold
union (tooling base, not a cast pedestal). Standalone print STLs are exported
with minZ=0 (plate bottom / frame bottom on the bed).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

ASSETS = Path(__file__).resolve().parent / "assets"
BLEND_STL = ASSETS / "moai_head_scan_152mm_v1_blend.stl"
BLEND_PREVIEW = ASSETS / "moai_head_scan_152mm_v1_blend_preview.ply"
MASTER_STL = ASSETS / "moai_mold_v1_master_with_base.stl"
FRAME_STL = ASSETS / "moai_mold_v1_pour_frame.stl"
BLEND_HEIGHT_MM = 152.4

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
OVER_APEX = 6.0  # nominal param; actual cover above exposed head is OVER_APEX + STATUE_SINK
STATUE_SINK = 0.5
SEG = 192


@dataclass(frozen=True)
class MoaiMoldDims:
    max_r_mm: float
    frame_id: float
    frame_od: float
    frame_len: float
    frame_gr_in: float
    frame_gr_out: float
    groove_width: float
    groove_depth: float
    clearance_per_side: float
    wall: float
    plate_d: float
    plate_t: float
    lip_d_in: float
    lip_d_out: float
    silicone_side_mm: float
    top_cover_mm: float  # actual cover above exposed head (= OVER_APEX + STATUE_SINK = 6.5)
    over_apex_param_mm: float
    statue_height_mm: float
    exposed_head_mm: float
    statue_sink_mm: float
    fill_above_plate_mm: float
    silicone_ml: float
    statue_cm3_in_cavity: float
    cavity_ml: float
    master_export_height_mm: float


def _load_statue() -> "trimesh.Trimesh":
    import trimesh

    m = trimesh.load(BLEND_STL, process=True)
    assert abs(float(m.extents[2]) - BLEND_HEIGHT_MM) < 0.05
    return m


def dims_for(statue=None) -> MoaiMoldDims:
    if statue is None:
        statue = _load_statue()
    v = statue.vertices
    max_r = float(np.sqrt(v[:, 0] ** 2 + v[:, 1] ** 2).max())
    frame_id = 2.0 * (max_r + SILICONE_SIDE)
    frame_gr_in = frame_id / 2 - CLR
    frame_gr_out = frame_id / 2 + FRAME_WALL + CLR
    li = frame_gr_out + LIP_CHANNEL
    lo = li + LIP_WIDTH
    plate_r = frame_gr_out + PLATE_RIM
    H = float(statue.extents[2])
    exposed = H - STATUE_SINK
    fill = H + OVER_APEX  # 158.4; seated frame inner top
    actual_cover = fill - exposed  # 6.5
    cav = math.pi * (frame_id / 2) ** 2 * fill
    # Approximate cavity displacement: total statue volume minus the thin submerged disk
    # (exact build uses manifold trim; prebuilt STL dims use this conservative estimate)
    # Prefer reading verification if building live:
    statue_cm3 = float(statue.volume) / 1000.0
    # Submerged ~0.5 mm of base: estimate as base_area * sink
    base = v[v[:, 2] < 0.5]
    if len(base) > 10:
        # convex hull area approx via bounding ellipse
        sub_cm3 = (math.pi * (0.5 * np.ptp(base[:, 0])) * (0.5 * np.ptp(base[:, 1])) * STATUE_SINK) / 1000.0
    else:
        sub_cm3 = 0.5
    in_cav = max(statue_cm3 - sub_cm3, 0.0)
    silicone_ml = cav / 1000.0 - in_cav
    return MoaiMoldDims(
        max_r_mm=max_r,
        frame_id=frame_id,
        frame_od=frame_id + 2 * FRAME_WALL,
        frame_len=fill + GR_DEPTH,
        frame_gr_in=frame_gr_in,
        frame_gr_out=frame_gr_out,
        groove_width=frame_gr_out - frame_gr_in,
        groove_depth=GR_DEPTH,
        clearance_per_side=CLR,
        wall=FRAME_WALL,
        plate_d=2 * plate_r,
        plate_t=PLATE_T,
        lip_d_in=2 * li,
        lip_d_out=2 * lo,
        silicone_side_mm=frame_id / 2 - max_r,
        top_cover_mm=actual_cover,
        over_apex_param_mm=OVER_APEX,
        statue_height_mm=H,
        exposed_head_mm=exposed,
        statue_sink_mm=STATUE_SINK,
        fill_above_plate_mm=fill,
        silicone_ml=silicone_ml,
        statue_cm3_in_cavity=in_cav,
        cavity_ml=cav / 1000.0,
        master_export_height_mm=PLATE_T + exposed,
    )


def _to_manifold(m):
    import manifold3d as mf

    mm = mf.Manifold(mf.Mesh(m.vertices.astype(np.float32), m.faces.astype(np.uint32)))
    if mm.status() != mf.Error.NoError:
        raise RuntimeError(mm.status())
    return mm


def _tomesh(man):
    import trimesh

    mesh = man.to_mesh()
    tm = trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts), process=True)
    if tm.volume < 0:
        tm.invert()
    return tm


@lru_cache(maxsize=2)
def build_parts() -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """Return {'master', 'pour_frame', 'statue'} as (vertices, faces) in mm, print pose minZ=0."""
    import manifold3d as mf

    # Prefer committed print-ready STLs
    if MASTER_STL.is_file() and FRAME_STL.is_file() and BLEND_STL.is_file():
        import trimesh

        st = trimesh.load(BLEND_STL, process=True)
        sm = trimesh.load(MASTER_STL, process=True)
        sf = trimesh.load(FRAME_STL, process=True)
        return {
            "statue": (np.asarray(st.vertices, float), np.asarray(st.faces, np.int64)),
            "master": (np.asarray(sm.vertices, float), np.asarray(sm.faces, np.int64)),
            "pour_frame": (np.asarray(sf.vertices, float), np.asarray(sf.faces, np.int64)),
        }

    statue = _load_statue()
    d = dims_for(statue)
    M = mf.Manifold
    st = statue.copy()
    st.vertices = st.vertices.copy()
    st.vertices[:, 2] -= STATUE_SINK
    plate_r = d.plate_d / 2
    li, lo = d.lip_d_in / 2, d.lip_d_out / 2
    plate = M.cylinder(PLATE_T, plate_r, plate_r, SEG).translate((0, 0, -PLATE_T))
    lip = M.revolve(
        mf.CrossSection([[(li, -0.5), (lo, -0.5), (lo, LIP_HEIGHT - LIP_CH), (lo - LIP_CH, LIP_HEIGHT),
                          (li + LIP_CH, LIP_HEIGHT), (li, LIP_HEIGHT - LIP_CH)]]),
        SEG,
    )
    ring = M.cylinder(GR_DEPTH + 1, d.frame_gr_out, d.frame_gr_out, SEG) - M.cylinder(
        GR_DEPTH + 1, d.frame_gr_in, d.frame_gr_in, SEG
    )
    master = (_to_manifold(st) + plate + lip) - ring.translate((0, 0, -GR_DEPTH))
    ri = d.frame_id / 2
    ro = ri + FRAME_WALL
    fill = d.fill_above_plate_mm
    z0 = -GR_DEPTH
    h = fill - z0
    frame = M.revolve(
        mf.CrossSection([[(ri + FRAME_CH, z0), (ro - FRAME_CH, z0), (ro, z0 + FRAME_CH), (ro, z0 + h),
                          (ri, z0 + h), (ri, z0 + FRAME_CH)]]),
        SEG,
    )
    sm = _tomesh(master)
    sf = _tomesh(frame)
    sm.vertices = sm.vertices.copy(); sf.vertices = sf.vertices.copy()
    sm.vertices[:, 2] -= sm.bounds[0, 2]
    sf.vertices[:, 2] -= sf.bounds[0, 2]
    return {
        "statue": (np.asarray(statue.vertices, float), np.asarray(statue.faces, np.int64)),
        "master": (np.asarray(sm.vertices, float), np.asarray(sm.faces, np.int64)),
        "pour_frame": (np.asarray(sf.vertices, float), np.asarray(sf.faces, np.int64)),
    }


def stl_bytes(part: str) -> bytes:
    if part == "statue":
        return BLEND_STL.read_bytes()
    prebuilt = {"master": MASTER_STL, "pour_frame": FRAME_STL}.get(part)
    if prebuilt is not None and prebuilt.is_file():
        return prebuilt.read_bytes()
    import trimesh

    v, f = build_parts()[part]
    return trimesh.Trimesh(v, f, process=False).export(file_type="stl")


def file_name(part: str) -> str:
    return {
        "statue": "moai_head_scan_152mm_v1_blend.stl",
        "master": "moai_mold_v1_master_with_base.stl",
        "pour_frame": "moai_mold_v1_pour_frame.stl",
    }[part]
