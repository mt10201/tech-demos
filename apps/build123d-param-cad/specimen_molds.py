"""Concrete test-specimen silicone mold masters (cube compressive / prism flexural), mm.

One printed master = rounded-rectangle base plate + N specimen positives standing on it, plus a
separate detachable pour frame. The seating is the proven electroculture tower v3 / Moai cross-section
(moai_mold constants, imported, NOT re-tuned): 0.25 mm/side frame clearance, 3.5 x 1.6 mm glue-bead
groove, 3.0 mm frame wall, 4.0 mm plate, 1.5 mm lip channel, 1.6 x 3.0 mm vertical outer sealing lip,
0.4 mm chamfers. The circular revolve is replaced by an identical-profile sweep around a rounded
rectangle (corner centres fixed, every offset ring shares them), so all cross-sections are the same.

Open-top casting: silicone is poured over the positives up to the fill line; the cured block is turned
over and each positive leaves an open cavity whose open side was the plate side. The positive's printed
top face becomes the cavity bottom (= one specimen face); its printed side walls become the other four.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

import numpy as np

from moai_mold import CLR, FRAME_CH, FRAME_WALL, GR_DEPTH, LIP_CH, LIP_CHANNEL, LIP_HEIGHT, LIP_WIDTH, PLATE_T

BED_XY = 150.0          # conservative usable Ender 2 bed (owner profile notes)
BED_Z = 200.0
PLATE_MARGIN = 1.0      # plate beyond the outer face of the lip (tower used 4.8; trimmed to fit 150 bed)
LIP_SINK = 0.5          # lip root sunk into plate for a manifold union (as tower/Moai)
POS_SINK = 1.0          # positive root sunk into plate for a manifold union (hidden in the plate)
CORNER_SEG = 24         # samples per 90 deg corner arc


@dataclass(frozen=True)
class SpecimenParams:
    kind: str = "cube"            # "cube" | "bar"
    a: float = 50.0               # cross-section edge (cube edge, or prism width = height)
    length: float = 50.0          # cube: = a ; bar: 4a
    nx: int = 2                   # positives along x
    ny: int = 2                   # positives along y
    gap: float = 10.0             # silicone between cavities and to the frame inner wall
    cover: float = 10.0           # silicone over the positives' tops
    corner_r: float = 10.0        # frame inner corner radius (<= gap keeps the corner gap >= gap)
    upright: bool = False         # bar only: stand prisms on end (lets 40x40x160 fit; vertical casting)


CUBE_DEFAULT = SpecimenParams("cube", 50.0, 50.0, 2, 2)
BAR_DEFAULT = SpecimenParams("bar", 27.5, 110.0, 1, 3)


def positive_size(p: SpecimenParams) -> Tuple[float, float, float]:
    if p.kind == "cube":
        return (p.a, p.a, p.a)
    if p.upright:
        return (p.a, p.a, p.length)
    return (p.length, p.a, p.a)


# --- profile offsets measured outward from the frame inner face (u = 0) ---------------------------
U_GR_IN = -CLR
U_GR_OUT = FRAME_WALL + CLR
U_LIP_IN = U_GR_OUT + LIP_CHANNEL
U_LIP_OUT = U_LIP_IN + LIP_WIDTH
U_PLATE = U_LIP_OUT + PLATE_MARGIN


@dataclass(frozen=True)
class SpecimenDims:
    kind: str
    specimen_mm: Tuple[float, float, float]
    count: int
    layout: str
    frame_inner_mm: Tuple[float, float]
    frame_inner_corner_r: float
    frame_outer_mm: Tuple[float, float]
    frame_height_mm: float
    plate_mm: Tuple[float, float]
    plate_corner_r: float
    groove_width: float
    groove_depth: float
    clearance_per_side: float
    lip_width: float
    lip_height: float
    lip_channel: float
    fill_above_plate_mm: float
    master_height_mm: float
    gap_between_mm: float
    gap_to_frame_mm: float
    gap_corner_mm: float
    top_cover_mm: float
    cavity_ml: float
    positives_ml: float
    silicone_ml: float
    master_fits_bed: bool
    master_margin_per_side_mm: float
    frame_fits_with_5mm_brim: bool
    master_fits_with_5mm_brim: bool


def _layout(p: SpecimenParams):
    sx, sy, sz = positive_size(p)
    W = p.nx * sx + (p.nx + 1) * p.gap
    D = p.ny * sy + (p.ny + 1) * p.gap
    centres = [(-W / 2 + p.gap + sx / 2 + i * (sx + p.gap), -D / 2 + p.gap + sy / 2 + j * (sy + p.gap))
               for i in range(p.nx) for j in range(p.ny)]
    return W, D, (sx, sy, sz), centres


def _rr_area(w, d, r):
    return w * d - (4 - math.pi) * r * r


def _ring(W, D, r0, u, seg=CORNER_SEG):
    """Rounded rectangle at offset u from the inner rounded rect (half sizes W/2, D/2, corner r0). CCW.
    Corner centres are shared by every offset so swept profiles stay identical."""
    cx, cy = W / 2 - r0, D / 2 - r0
    r = r0 + u
    pts = []
    for (sx, sy, a0) in ((1, 1, 0.0), (-1, 1, 0.5 * math.pi), (-1, -1, math.pi), (1, -1, 1.5 * math.pi)):
        for k in range(seg + 1):
            t = a0 + 0.5 * math.pi * k / seg
            pts.append((sx * cx + r * math.cos(t), sy * cy + r * math.sin(t)))
    return np.asarray(pts)


def _poly_area(pts):
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def dims(p: SpecimenParams) -> SpecimenDims:
    W, D, (sx, sy, sz), c = _layout(p)
    r0 = p.corner_r
    fill = sz + p.cover
    PW, PD = W + 2 * U_PLATE, D + 2 * U_PLATE
    cav = _poly_area(_ring(W, D, r0, 0.0)) * fill / 1000.0  # polygon actually built
    pos = len(c) * sx * sy * sz / 1000.0
    # corner gap: corner positive's outer corner to the inner corner arc
    ccx, ccy = W / 2 - r0, D / 2 - r0
    px, py = W / 2 - p.gap, D / 2 - p.gap
    dcorner = r0 - math.hypot(max(px - ccx, 0), max(py - ccy, 0)) if (px > ccx and py > ccy) else p.gap
    margin = (BED_XY - max(PW, PD)) / 2
    return SpecimenDims(
        kind=p.kind, specimen_mm=(sx, sy, sz) if p.kind == "cube" else (p.length, p.a, p.a),
        count=len(c), layout=f"{p.nx} x {p.ny}" + (" upright" if p.upright and p.kind == "bar" else ""),
        frame_inner_mm=(W, D), frame_inner_corner_r=r0,
        frame_outer_mm=(W + 2 * FRAME_WALL, D + 2 * FRAME_WALL), frame_height_mm=fill + GR_DEPTH,
        plate_mm=(PW, PD), plate_corner_r=r0 + U_PLATE,
        groove_width=U_GR_OUT - U_GR_IN, groove_depth=GR_DEPTH, clearance_per_side=CLR,
        lip_width=LIP_WIDTH, lip_height=LIP_HEIGHT, lip_channel=LIP_CHANNEL,
        fill_above_plate_mm=fill, master_height_mm=PLATE_T + sz,
        gap_between_mm=p.gap, gap_to_frame_mm=p.gap, gap_corner_mm=min(dcorner, p.gap) - r0 * (1 - math.cos(math.pi / (4 * CORNER_SEG))),
        top_cover_mm=p.cover,
        cavity_ml=cav, positives_ml=pos, silicone_ml=cav - pos,
        master_fits_bed=max(PW, PD) <= BED_XY and PLATE_T + sz <= BED_Z,
        master_margin_per_side_mm=margin,
        frame_fits_with_5mm_brim=max(W, D) + 2 * FRAME_WALL + 10 <= BED_XY and fill + GR_DEPTH <= BED_Z,
        master_fits_with_5mm_brim=max(PW, PD) + 10 <= BED_XY,
    )


def _sweep(W, D, r0, profile: List[Tuple[float, float]]):
    """Analogue of revolve: closed (u, z) profile swept around the rounded rectangle -> trimesh ring."""
    import trimesh

    rings = [_ring(W, D, r0, u) for (u, _) in profile]
    n = len(rings[0]); m = len(profile)
    V = np.concatenate([np.column_stack([rg, np.full(n, z)]) for rg, (_, z) in zip(rings, profile)])
    F = []
    for a in range(m):
        b = (a + 1) % m
        for i in range(n):
            j = (i + 1) % n
            F += [(a * n + i, b * n + i, b * n + j), (a * n + i, b * n + j, a * n + j)]
    tm = trimesh.Trimesh(V, np.asarray(F), process=True)
    tm.merge_vertices(); tm.update_faces(tm.nondegenerate_faces()); tm.remove_unreferenced_vertices()
    if tm.volume < 0:
        tm.invert()
    return tm


def _man(tm):
    import manifold3d as mf

    mm = mf.Manifold(mf.Mesh(np.asarray(tm.vertices, np.float32), np.asarray(tm.faces, np.uint32)))
    if mm.status() != mf.Error.NoError:
        raise RuntimeError(mm.status())
    return mm


def _tm(man):
    import trimesh

    mesh = man.to_mesh()
    tm = trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts), process=True)
    if tm.volume < 0:
        tm.invert()
    return tm


def build(p: SpecimenParams) -> Dict[str, "trimesh.Trimesh"]:
    """{'master', 'pour_frame'} trimeshes, print pose (plate / frame bottom on z=0), centred in x,y."""
    import manifold3d as mf

    W, D, (sx, sy, sz), centres = _layout(p)
    r0 = p.corner_r
    d = dims(p)
    plate_pts = _ring(W, D, r0, U_PLATE)
    plate = mf.Manifold.extrude(mf.CrossSection([plate_pts[:-1].tolist()]), PLATE_T).translate((0, 0, -PLATE_T))
    lip = _man(_sweep(W, D, r0, [(U_LIP_IN, -LIP_SINK), (U_LIP_OUT, -LIP_SINK), (U_LIP_OUT, LIP_HEIGHT - LIP_CH),
                                  (U_LIP_OUT - LIP_CH, LIP_HEIGHT), (U_LIP_IN + LIP_CH, LIP_HEIGHT),
                                  (U_LIP_IN, LIP_HEIGHT - LIP_CH)]))
    groove = _man(_sweep(W, D, r0, [(U_GR_IN, -GR_DEPTH), (U_GR_OUT, -GR_DEPTH), (U_GR_OUT, 1.0), (U_GR_IN, 1.0)]))
    master = plate + lip
    for (x, y) in centres:  # sharp, square positives (no fillet, no draft)
        master = master + mf.Manifold.cube((sx, sy, sz + POS_SINK)).translate((x - sx / 2, y - sy / 2, -POS_SINK))
    master = master - groove
    fill = d.fill_above_plate_mm
    z0 = -GR_DEPTH
    frame = _sweep(W, D, r0, [(FRAME_CH, z0), (FRAME_WALL - FRAME_CH, z0), (FRAME_WALL, z0 + FRAME_CH),
                              (FRAME_WALL, fill), (0.0, fill), (0.0, z0 + FRAME_CH)])
    frame = _tm(_man(frame))
    sm = _tm(master)
    out = {}
    for k, tm in (("master", sm), ("pour_frame", frame)):
        tm.vertices = tm.vertices - [0, 0, tm.bounds[0, 2]]
        out[k] = tm
    return out


def check(tm) -> dict:
    parts = tm.split(only_watertight=False)
    e = int(tm.euler_number)
    return dict(watertight=bool(tm.is_watertight), winding_consistent=bool(tm.is_winding_consistent),
                bodies=len(parts), euler=e, genus=(2 - e) // 2, volume_ml=round(float(tm.volume) / 1000, 3),
                min_z=round(float(tm.bounds[0, 2]), 4),
                footprint_mm=[round(float(x), 2) for x in tm.extents[:2]], height_mm=round(float(tm.extents[2]), 2),
                triangles=int(len(tm.faces)))


def stl_bytes(tm) -> bytes:
    return tm.export(file_type="stl")


def dims_dict(p: SpecimenParams) -> dict:
    return asdict(dims(p))
