"""Silicone mold masters (positives) for the grooved Rodin torus. Units: **mm**.

Layout (like the owner's reference photo)::

         ┌──────────── pour frame (separate print) ────────────┐
         │  key ●                                     ● key    │
         │            ╭──── half grooved torus ────╮           │
         │            │   (flat equator face down) │           │
         │  key ●     ╰────────────────────────────╯   ● key   │
         └────────────────────── plate ──────────────────────┘

* **Master A** = square plate (top face at z = 0) + the *top* half of the
  grooved torus (z ≥ 0) + 4 hemisphere key **bumps** near the corners.  The
  plate runs under the donut hole, so the silicone fills the hole.
* **Master B** = the same plate with 4 hemisphere key **sockets** + the *bottom*
  half of the torus turned over by a 180° rotation about X, (x, y, z) →
  (x, −y, −z), a proper rotation, so the casting is not mirrored.  Bumps in A
  give dimples in silicone A, sockets in B give bumps in silicone B, and the two
  silicone halves register. The keys sit at (±a, ±a), which maps onto itself under
  that rotation.
* **Pour frame**: a separate one-piece square wall.  ``frame_style``:

  - ``"around"`` (default, like the photo): a plain plate with the frame
    standing on the table around it, ``clearance`` from the plate edge.  Frame
    outer = plate + 2·(clearance + wall); with the default 7 mm margin that is
    145.6 mm, so the frame **and** the plates fit a 150 × 150 mm bed in one piece.
  - ``"ledge"``: the plate gets a raised island (the pour floor) and a lowered
    perimeter ledge ``wall + clearance`` wide; the frame drops over the island
    and sits on the ledge.  Same footprint, but the frame self-locates and the
    silicone has to climb the step before it can leak.

The torus solid comes from ``boolean_mesh.grooved_solid`` (the same smooth
manifold3d mesh as the STL), scaled to mm and split at the equator z = 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Dict, Tuple

import numpy as np

from boolean_mesh import EXPORT_KW, PREVIEW_KW, _to_manifold, grooved_solid
from geometry import MM_PER_IN, TorusParams, validate

ENDER2_BED_MM = (150.0, 150.0, 200.0)  # Creality Ender-2 spec print volume (X, Y, Z)
OVERLAP = 0.5  # mm: the half torus / key spheres sink this far into the plate (no coplanar faces)


@dataclass(frozen=True)
class MoldParams:
    """All mm."""

    margin: float = 7.0  # torus outer edge → pour-cavity wall (= silicone side-wall thickness)
    plate_thickness: float = 4.0  # floor under the pour cavity (master A)
    key_radius: float = 8.0  # hemisphere registration keys
    key_edge_gap: float = 3.0  # key edge → cavity wall
    clearance: float = 0.3  # frame inner face ↔ plate island
    wall: float = 3.0  # frame wall thickness
    cover: float = 10.0  # silicone above the top of the half torus
    ledge_height: float = 2.0  # frame_style "ledge": island stands this far above the ledge
    frame_style: str = "around"  # "around" | "ledge"
    socket_floor: float = 2.0  # master B: plastic left under each key socket


def validate_mold(t: TorusParams, m: MoldParams) -> None:
    validate(t)
    if m.frame_style not in ("ledge", "around"):
        raise ValueError("frame_style must be 'ledge' or 'around'")
    for k in ("margin", "plate_thickness", "key_radius", "clearance", "wall", "cover"):
        if getattr(m, k) <= 0:
            raise ValueError(f"{k} must be > 0")
    if m.frame_style == "ledge" and not (0 < m.ledge_height < m.plate_thickness):
        raise ValueError("ledge_height must be between 0 and the plate thickness")
    if key_torus_gap(t, m) <= 0:
        raise ValueError("keys overlap the torus: increase the margin or reduce the key radius")


# ---- layout ------------------------------------------------------------------

def torus_outer_radius_mm(t: TorusParams) -> float:
    return (t.major_radius + t.tube_radius) * MM_PER_IN


def half_height_mm(t: TorusParams) -> float:
    return t.tube_radius * MM_PER_IN


def island_half(t: TorusParams, m: MoldParams) -> float:
    """Half side of the plate's pour floor (the island / the plain plate)."""
    return torus_outer_radius_mm(t) + m.margin


def cavity_half(t: TorusParams, m: MoldParams) -> float:
    """Half side of the silicone cavity = frame inner face."""
    return island_half(t, m) + m.clearance


def key_offset(t: TorusParams, m: MoldParams) -> float:
    """Keys sit at (±a, ±a, 0)."""
    return island_half(t, m) - m.key_edge_gap - m.key_radius


def key_torus_gap(t: TorusParams, m: MoldParams) -> float:
    """Closest distance between a key's edge and the torus' outer edge."""
    return math.sqrt(2) * key_offset(t, m) - m.key_radius - torus_outer_radius_mm(t)


def plate_thickness_b(m: MoldParams) -> float:
    """Master B needs room for the sockets: max(plate, key radius + floor)."""
    return max(m.plate_thickness, m.key_radius + m.socket_floor)


def plate_half(t: TorusParams, m: MoldParams) -> float:
    hi = island_half(t, m)
    return hi + m.clearance + m.wall if m.frame_style == "ledge" else hi


def frame_dims(t: TorusParams, m: MoldParams) -> Tuple[float, float, float]:
    """(outer side, inner side, height) of the pour frame."""
    inner = 2 * cavity_half(t, m)
    outer = inner + 2 * m.wall
    if m.frame_style == "ledge":
        h = m.ledge_height + half_height_mm(t) + m.cover
    else:
        h = m.plate_thickness + half_height_mm(t) + m.cover
    return outer, inner, h


def part_sizes(t: TorusParams, m: MoldParams) -> Dict[str, Tuple[float, float, float]]:
    """Bounding boxes (X, Y, Z mm) of each printable part as printed."""
    s = 2 * plate_half(t, m)
    hh = half_height_mm(t)
    fo, _, fh = frame_dims(t, m)
    return {
        "master_A": (s, s, m.plate_thickness + hh),
        "master_B": (s, s, plate_thickness_b(m) + hh),
        "pour_frame": (fo, fo, fh),
    }


def fits_bed(size, bed=ENDER2_BED_MM) -> bool:
    return all(a <= b + 1e-9 for a, b in zip(size, bed))


def silicone_volume_cm3(t: TorusParams, m: MoldParams, master_above_floor_mm3: float) -> float:
    """Silicone for one half: cavity box from the pour floor to the top of the
    frame minus the master above the floor."""
    c = 2 * cavity_half(t, m)
    return (c * c * (half_height_mm(t) + m.cover) - master_above_floor_mm3) / 1000.0


# ---- solids (manifold3d) ------------------------------------------------------

def _box(x0, x1, y0, y1, z0, z1):
    import manifold3d as mf

    return mf.Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))


def _plate(t: TorusParams, m: MoldParams, thickness: float):
    hi = island_half(t, m)
    if m.frame_style == "around":
        return _box(-hi, hi, -hi, hi, -thickness, 0.0)
    ph = plate_half(t, m)
    base = _box(-ph, ph, -ph, ph, -thickness, -m.ledge_height)
    island = _box(-hi, hi, -hi, hi, -m.ledge_height - OVERLAP, 0.0)
    return base + island


def _keys(t: TorusParams, m: MoldParams, z_cut: float | None, segments: int):
    import manifold3d as mf

    a = key_offset(t, m)
    out = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            s = mf.Manifold.sphere(m.key_radius, segments).translate((sx * a, sy * a, 0.0))
            if z_cut is not None:
                s = s.trim_by_plane((0.0, 0.0, 1.0), z_cut)
            out.append(s)
    return mf.Manifold.batch_boolean(out, mf.OpType.Add)


def torus_mm(t: TorusParams, hires: bool = True):
    """The grooved torus (same mesh as the STL) as a manifold in mm."""
    v, f = grooved_solid(t, **(EXPORT_KW if hires else PREVIEW_KW))
    return _to_manifold(v * MM_PER_IN, f)


def torus_halves(t: TorusParams, hires: bool = True):
    """(top, bottom_flipped): both stand on z = 0 with OVERLAP below it.

    bottom_flipped = bottom half rotated 180° about X: (x, y, z) → (x, −y, −z).
    """
    tor = torus_mm(t, hires)
    top = tor.trim_by_plane((0.0, 0.0, 1.0), -OVERLAP)
    rot = tor.transform(np.array([[1, 0, 0, 0], [0, -1, 0, 0], [0, 0, -1, 0]], dtype=float))
    bottom = rot.trim_by_plane((0.0, 0.0, 1.0), -OVERLAP)
    return top, bottom


def masters(t: TorusParams, m: MoldParams, hires: bool = True, key_segments: int = 128):
    """Return {'master_A', 'master_B', 'pour_frame'} manifolds (mm)."""
    validate_mold(t, m)
    top, bottom = torus_halves(t, hires)
    # bumps: sphere trimmed just below the floor so it fuses without coplanar faces
    a = _plate(t, m, m.plate_thickness) + top + _keys(t, m, -OVERLAP, key_segments)
    b = (_plate(t, m, plate_thickness_b(m)) + bottom) - _keys(t, m, None, key_segments)
    fo, fi, fh = frame_dims(t, m)
    z0 = -m.ledge_height if m.frame_style == "ledge" else -m.plate_thickness
    frame = _box(-fo / 2, fo / 2, -fo / 2, fo / 2, z0, z0 + fh) - _box(
        -fi / 2, fi / 2, -fi / 2, fi / 2, z0 - 1, z0 + fh + 1)
    return {"master_A": a, "master_B": b, "pour_frame": frame}


def to_arrays(man) -> Tuple[np.ndarray, np.ndarray]:
    mesh = man.to_mesh64()
    return np.asarray(mesh.vert_properties)[:, :3].astype(float), np.asarray(mesh.tri_verts).astype(np.int64)


def print_pose(V: np.ndarray) -> np.ndarray:
    """Translate so the part sits on z = 0 (as printed)."""
    return V - np.array([0.0, 0.0, V[:, 2].min()])


def stl_bytes_mm(man) -> bytes:
    import trimesh

    V, F = to_arrays(man)
    return trimesh.Trimesh(print_pose(V), F, process=False).export(file_type="stl")


def above_floor_volume(man) -> float:
    """Volume (mm³) of a master above its pour floor (z > 0)."""
    return man.trim_by_plane((0.0, 0.0, 1.0), 0.0).volume()


def halves_identical(t: TorusParams, hires: bool = False) -> Tuple[bool, float]:
    """Is the flipped bottom half the same solid as the top half?

    Returns (identical, symmetric-difference volume / half volume)."""
    top, bottom = torus_halves(t, hires)
    xor = (top - bottom).volume() + (bottom - top).volume()
    rel = xor / top.volume()
    return rel < 2e-3, rel


# ---- STEP (exact B-rep, slow) ------------------------------------------------

def _mesh_volumes(t: TorusParams, m: MoldParams) -> Tuple[float, float]:
    """Volumes (mm³) of masters A and B from the mesh path, to check the B-rep."""
    p = masters(t, m, hires=False, key_segments=64)
    return p["master_A"].volume(), p["master_B"].volume()


def master_step_bytes(t: TorusParams, m: MoldParams, progress=None, torus_solid_mm=None) -> Dict[str, bytes]:
    """Exact B-rep masters A and B as mm STEP files.

    Uses ``rodin_torus.finished_solid`` (24 sequential OpenCascade cuts,
    ~4–5 min) once, splits it at z = 0 and fuses each half with the plate and
    keys in OpenCascade."""
    import tempfile
    from pathlib import Path

    from build123d import Box, Pos, Rot, Sphere, Unit, export_step

    from rodin_torus import finished_solid

    validate_mold(t, m)
    tor = torus_solid_mm if torus_solid_mm is not None else finished_solid(t, progress).scale(MM_PER_IN)
    # ``split`` silently returns the whole grooved torus, so intersect with a
    # half-space box instead (reaching OVERLAP past z = 0, like the mesh path).
    # A general master B is built in the torus' own frame (bottom half, plate
    # *above* z = 0) and turned over at the end.
    big = 4 * (torus_outer_radius_mm(t) + m.margin)
    hh = half_height_mm(t) + 5 + OVERLAP

    def slab(z0, z1, half):
        return Pos(0, 0, (z0 + z1) / 2) * Box(2 * half, 2 * half, z1 - z0)

    def plate(th, up=False):
        """Plate under the flat face: z ∈ [−th, 0], or mirrored to [0, th] if ``up``."""
        hi = island_half(t, m)
        if m.frame_style == "around":
            zs = [(-th, 0.0, hi)]
        else:
            zs = [(-th, -m.ledge_height, plate_half(t, m)), (-m.ledge_height, 0.0, hi)]
        out = None
        for z0, z1, h in zs:
            p = slab(-z1, -z0, h) if up else slab(z0, z1, h)
            out = p if out is None else out + p
        return out

    top = tor & slab(-OVERLAP, hh, big)
    bottom = tor & slab(-hh, OVERLAP, big)

    a_off = key_offset(t, m)
    pos = [(sx * a_off, sy * a_off) for sx in (-1, 1) for sy in (-1, 1)]
    bumps = [(Pos(x, y, 0) * Sphere(m.key_radius)) & slab(-OVERLAP, m.key_radius + 1, big) for x, y in pos]
    sockets = [Pos(x, y, 0) * Sphere(m.key_radius) for x, y in pos]
    tb = plate_thickness_b(m)
    a = plate(m.plate_thickness).fuse(top, *bumps).clean()
    if halves_identical(t)[0]:
        # The turned-over bottom half equals the top half (checked on the mesh),
        # and OpenCascade fuses the top half reliably, but it silently dropped the
        # plate when fusing it with the bottom half of the finished torus.
        b = plate(tb).fuse(top).clean().cut(*sockets)
        flip = False
    else:
        b = plate(tb, up=True).fuse(bottom).clean().cut(*sockets)
        flip = True
    want_a, want_b = _mesh_volumes(t, m)
    for name, shape, want in (("A", a, want_a), ("B", b, want_b)):
        if len(shape.solids()) != 1 or not shape.is_valid or abs(shape.volume / want - 1) > 0.01:
            raise RuntimeError(f"OpenCascade boolean for master {name} failed "
                               f"({shape.volume / 1000:.1f} cm³, expected {want / 1000:.1f})")
    if flip:
        b = Rot(180, 0, 0) * b  # flat side down, like the STL: (x, y, z) → (x, −y, −z)
    fo, fi, fh = frame_dims(t, m)
    frame = Pos(0, 0, fh / 2) * Box(fo, fo, fh) - Pos(0, 0, fh / 2) * Box(fi, fi, fh + 2)
    # same print pose as the STLs: each part's underside on z = 0
    a = Pos(0, 0, m.plate_thickness) * a
    b = Pos(0, 0, plate_thickness_b(m)) * b
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, shape in (("mold_master_A_mm.step", a), ("mold_master_B_mm.step", b),
                            ("pour_frame_mm.step", frame)):
            p = Path(tmp) / name
            export_step(shape, str(p), unit=Unit.MM)
            out[name] = p.read_bytes()
    return out
