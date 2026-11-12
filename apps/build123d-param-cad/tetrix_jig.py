"""Tetrix (Sierpinski tetrahedron) brazing jigs for twisted copper rods, mm.

The piece: a level-L tetrix of outer edge E (a royal-cubit harmonic, 523.6 / 2**n) made of straight rods,
one rod per edge of each smallest tetrahedron (edge e = E / 2**L, 6 * 4**L rods, joints brazed).

PLA cannot see brazing heat (Sil-Fos ~700 C), so the jigs only POSITION rods: every jig surface holds a
rod near its middle, stays >= MIN_JOINT_CLEAR from every joint, and every rod channel is open straight
up (+z), so the tied piece lifts out vertically before it is brazed elsewhere.

Parts (all single watertight bodies, print pose on z = 0, no supports):
  gauge          rod length gauge: end-stop cut channel(s) + a straightening groove
  tetra_jig      single smallest-tetrahedron jig: 3 base cradles + 3 sloped pillars under the upper rods
  assembly_<E'>  one plate per assembly stage: cradles under every base-layer rod of the 3 lower units and
                 posts under the base rods of the top unit (only where a post clears everything below it)
  rods_reference unioned cylinders of the rods as cut (visualisation only, not a printable part)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

import numpy as np

CUBIT = 523.6
BED = 235.0               # Ender usable bed (owner, Nov 12 2026)
BED_KEEP = 225.0          # keep parts within this
BED_Z = 200.0
MIN_JOINT_CLEAR = 6.0     # every jig surface this far from every joint
Z0 = 14.0                 # base-rod axis height above the jig plate (room to wrap binding wire under joints)
PLATE_T = 3.0
CRADLE_W = 8.0            # cradle / pillar width across the rod
CRADLE_TOP = 1.0          # material above the rod axis beyond the channel radius (side-wall top)
CRADLE_LEN_MAX = 20.0     # channel length along the rod
JOINT_HOLE_R = 9.0        # plate relief under each base joint for wire wrapping
SEG = 48


def cubit_edges() -> List[float]:
    return [CUBIT / 2 ** n for n in range(1, 6)]


@dataclass(frozen=True)
class TetrixParams:
    edge: float = CUBIT / 4          # outer edge E (130.9)
    level: int = 1
    rod_d: float = 2.8               # twisted pair of 16 AWG (2 x 1.29 mm) envelope
    clearance: float = 0.3           # channel width = rod_d + clearance (diametral)
    joint_allowance: float = 1.0     # cut length = small edge - allowance (half at each end)


DEFAULT = TetrixParams()


# ----------------------------------------------------------------------------------------- geometry
def tetra_vertices(e: float, z0: float = Z0, centre=(0.0, 0.0)) -> np.ndarray:
    """Regular tetrahedron standing on a face: 3 base corners at z0 (one on +y), apex above the centroid."""
    R = e / math.sqrt(3)
    H = e * math.sqrt(2 / 3)
    cx, cy = centre
    base = [(cx + R * math.cos(math.radians(90 + 120 * k)), cy + R * math.sin(math.radians(90 + 120 * k)), z0)
            for k in range(3)]
    return np.array(base + [(cx, cy, z0 + H)], float)


def subdivide(V: np.ndarray, level: int) -> List[np.ndarray]:
    """Smallest tetrahedra (vertex arrays, same order: 3 base + apex) of a level-`level` tetrix."""
    if level == 0:
        return [V]
    out = []
    for i in range(4):
        out += subdivide((V + V[i]) / 2, level - 1)
    return out


def edges_of(tets: List[np.ndarray]) -> List[Tuple[np.ndarray, np.ndarray]]:
    pairs = [(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)]
    return [(t[a], t[b]) for t in tets for a, b in pairs]


def joints_of(tets: List[np.ndarray]) -> np.ndarray:
    pts = np.vstack(tets)
    return np.unique(np.round(pts, 6), axis=0)


def rods_of(tets, allowance: float):
    """(start, end) of each rod as cut: edge shortened by allowance/2 at each end."""
    out = []
    for p, q in edges_of(tets):
        u = (q - p) / np.linalg.norm(q - p)
        out.append((p + u * allowance / 2, q - u * allowance / 2))
    return out


@dataclass(frozen=True)
class TetrixDims:
    edge: float
    level: int
    small_edge: float
    rod_count: int
    rod_cut_length: float
    joint_count: int
    rod_d: float
    channel_d: float
    wire_per_rod_mm: float
    total_rod_mm: float
    total_wire_mm_incl_3pct: float
    alt_continuous_outer_edges: dict
    stages: List[float]
    height: float


def dims(p: TetrixParams) -> TetrixDims:
    e = p.edge / 2 ** p.level
    tets = subdivide(tetra_vertices(p.edge, 0.0), p.level)
    n = len(tets) * 6
    cut = e - p.joint_allowance
    total = n * cut
    # 18-rod option (level 1): each outer edge one continuous rod (E - allowance) replaces 2 short rods
    n_out_short = 6 * 2 ** p.level          # short rods lying on the 6 outer edges
    alt_n = n - n_out_short + 6
    alt_total = (n - n_out_short) * cut + 6 * (p.edge - p.joint_allowance)
    return TetrixDims(
        edge=round(p.edge, 4), level=p.level, small_edge=round(e, 4), rod_count=n, rod_cut_length=round(cut, 3),
        joint_count=len(joints_of(tets)), rod_d=p.rod_d, channel_d=round(p.rod_d + p.clearance, 3),
        wire_per_rod_mm=round(cut * 1.03, 2),
        total_rod_mm=round(total, 1), total_wire_mm_incl_3pct=round(2 * total * 1.03, 1),
        alt_continuous_outer_edges=dict(rods=alt_n, short=n - n_out_short, short_len=round(cut, 3),
                                        long=6, long_len=round(p.edge - p.joint_allowance, 3),
                                        total_wire_mm_incl_3pct=round(2 * alt_total * 1.03, 1)),
        stages=[round(e * 2 ** k, 4) for k in range(1, p.level + 1)],
        height=round(p.edge * math.sqrt(2 / 3), 3))


# ----------------------------------------------------------------------------------------- manifold helpers
def _mf():
    import manifold3d as mf
    return mf


def _frame(u):
    u = u / np.linalg.norm(u)
    a = np.array([0, 0, 1.0]) if abs(u[2]) < 0.9 else np.array([1.0, 0, 0])
    x = np.cross(a, u); x /= np.linalg.norm(x)
    y = np.cross(u, x)
    return x, y, u


def _cyl(p, q, r, ext=0.0):
    mf = _mf()
    p, q = np.asarray(p, float), np.asarray(q, float)
    L = np.linalg.norm(q - p)
    x, y, u = _frame(q - p)
    p0 = p - u * ext
    M = np.column_stack([x, y, u, p0])
    return mf.Manifold.cylinder(L + 2 * ext, r, r, SEG).transform(M.tolist())


def _prism(poly_xy, z1, z0=0.0):
    mf = _mf()
    cs = mf.CrossSection([np.asarray(poly_xy, float).tolist()])
    return mf.Manifold.extrude(cs, z1 - z0).translate((0, 0, z0))


def _cradle(a, b, rc, length):
    """Block under rod axis a->b at its midpoint, rod channel open straight up. Returns (solid, channel cutter)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = (a + b) / 2
    u = (b - a) / np.linalg.norm(b - a)
    uxy = np.array([u[0], u[1], 0.0]); uxy /= np.linalg.norm(uxy)
    v = np.array([-uxy[1], uxy[0], 0.0])
    half_l = length / 2 * math.hypot(u[0], u[1])      # footprint along the rod's plan direction
    w = CRADLE_W / 2
    poly = [m + s * half_l * uxy + t * w * v for s, t in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    top = m[2] + (rc + CRADLE_TOP) / max(1e-9, math.cos(math.asin(min(1.0, abs(u[2]))))) + 2 * half_l * abs(u[2]) + 5
    blk = _prism([(q[0], q[1]) for q in poly], top, 0.0)
    n = np.cross(u, v); n /= np.linalg.norm(n)           # up-normal of the plane containing the rod and v
    if n[2] < 0:
        n = -n
    off = float(n @ m) + rc + CRADLE_TOP
    blk = blk.trim_by_plane((-n).tolist(), -off)          # keep the side below the plane
    c0 = _cyl(m - u * length, m + u * length, rc)
    mf = _mf()
    chan = mf.Manifold.batch_hull([c0, c0.translate((0, 0, 200))])
    return blk, chan


def _tm(man):
    import trimesh
    mesh = man.to_mesh()
    tm = trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts), process=False)
    tm.merge_vertices()
    parts = tm.split(only_watertight=False)
    if len(parts) > 1:  # drop zero-volume back-to-back face pairs manifold can leave at tangent cuts
        import trimesh as _t
        tm = _t.util.concatenate([q for q in parts if abs(q.volume) > 1e-6])
    if tm.volume < 0:
        tm.invert()
    return tm


def _man(tm):
    mf = _mf()
    return mf.Manifold(mf.Mesh(np.asarray(tm.vertices, np.float32), np.asarray(tm.faces, np.uint32)))


def _cradle_len(rod_len):
    return float(min(CRADLE_LEN_MAX, max(8.0, rod_len - 2 * (MIN_JOINT_CLEAR + 4.0))))


def _plate(xy_hull: np.ndarray, holes_xy: np.ndarray, margin: float):
    mf = _mf()
    cs = mf.CrossSection.hull_points(np.asarray(xy_hull, float)[:, :2].tolist()).offset(margin, mf.JoinType.Round)
    for h in holes_xy:
        cs = cs - mf.CrossSection.circle(JOINT_HOLE_R, SEG).translate((float(h[0]), float(h[1])))
    return mf.Manifold.extrude(cs, PLATE_T)


# ----------------------------------------------------------------------------------------- parts
def gauge(p: TetrixParams):
    """Rod length gauge. Row A: short cut channel (stop -> cut face = rod cut length). Row B: long cut channel
    (E - allowance, for the 18-rod continuous-outer-edge option). Row C: straightening groove, open both ends."""
    mf = _mf()
    d = dims(p)
    rc = (p.rod_d + p.clearance) / 2
    T, STOP, PITCH, M = 8.0, 6.0, 10.0, 6.0
    Ls, Ll = d.rod_cut_length, p.edge - p.joint_allowance
    long_ok = STOP + Ll <= BED_KEEP
    xs_end = STOP + Ls
    xl_end = STOP + Ll if long_ok else xs_end + 20
    rows = {"C": M, "B": M + PITCH, "A": M + 2 * PITCH}
    W_long = rows["B"] + M - 1                       # rows C, B over the long section
    W = rows["A"] + M
    body = mf.Manifold.cube((xl_end, W_long, T)) + mf.Manifold.cube((xs_end, W, T))
    zc = T - rc - 0.4                                   # rod sits just below the top surface
    def chan(y, x0, x1):
        c = _cyl((x0, y, zc), (x1, y, zc), rc)
        return mf.Manifold.batch_hull([c, c.translate((0, 0, 50))])
    body = body - chan(rows["A"], STOP, xs_end + 5)
    if long_ok:
        body = body - chan(rows["B"], STOP, xl_end + 5)
    body = body - chan(rows["C"], -5, xl_end + 5)
    # V finger notch across the short cut face is not needed; flush-cut against the face.
    return _tm(body), dict(rows_y=rows, short_cut=Ls, long_cut=Ll if long_ok else None, stop=STOP,
                           size=(xl_end, W, T))


def tetra_jig(p: TetrixParams):
    """Jig for one smallest tetrahedron, base face down; returns (jig, rods_in_place, joints)."""
    mf = _mf()
    d = dims(p)
    e = d.small_edge
    V = tetra_vertices(e, Z0)
    rc = (p.rod_d + p.clearance) / 2
    rods = rods_of([V], p.joint_allowance)
    L = _cradle_len(d.rod_cut_length)
    solids, cuts = [], []
    for a, b in rods:
        s, c = _cradle(a, b, rc, L)
        solids.append(s); cuts.append(c)
    feet = np.array([[x, y] for s in solids for (x, y, _) in _tm(s).vertices])
    plate = _plate(feet, V[:3], 2.0)
    jig = mf.Manifold.batch_boolean([plate] + solids, mf.OpType.Add)
    jig = jig - mf.Manifold.batch_boolean(cuts, mf.OpType.Add)
    return _tm(jig), rods, V


def assembly_plate(p: TetrixParams, stage_edge: float):
    """Plate for joining 4 sub-units (edge stage_edge/2) into one of edge stage_edge."""
    mf = _mf()
    d = dims(p)
    sub_level = int(round(math.log2(stage_edge / d.small_edge))) - 1
    V = tetra_vertices(stage_edge, Z0)
    units = [(V + V[i]) / 2 for i in range(4)]
    rc = (p.rod_d + p.clearance) / 2
    tets_all = subdivide(V, sub_level + 1)
    rods = rods_of(tets_all, p.joint_allowance)
    joints = joints_of(tets_all)
    L = _cradle_len(d.rod_cut_length)
    solids, cuts, held = [], [], []
    top_base_z = units[3][0, 2]
    # cradles under every rod lying in the bottom plane
    for a, b in rods:
        if abs(a[2] - Z0) < 1e-6 and abs(b[2] - Z0) < 1e-6:
            s, c = _cradle(a, b, rc, L); solids.append(s); cuts.append(c); held.append(("base", a, b))
    # posts under the top unit's base rods, only where the post clears all lower rods' vertical sweep
    lower = [(a, b) for a, b in rods if max(a[2], b[2]) < top_base_z - 1e-6 or
             (min(a[2], b[2]) < top_base_z - 1e-6)]
    posts = []
    for a, b in rods:
        if abs(a[2] - top_base_z) < 1e-6 and abs(b[2] - top_base_z) < 1e-6:
            s, c = _cradle(a, b, rc, min(L, 8.0))
            ts = _tm(s)
            ok = True
            for la, lb in lower:   # swept-up rod (hull of rod and rod raised) must not touch the post
                cyl = _cyl(la, lb, p.rod_d / 2 + 1.0)
                sweep = mf.Manifold.batch_hull([cyl, cyl.translate((0, 0, 300))])
                if (s ^ sweep).volume() > 1e-6:
                    ok = False; break
            if ok:
                posts.append((s, c, a, b))
    for s, c, a, b in posts:
        solids.append(s); cuts.append(c); held.append(("top", a, b))
    base_joints = joints[np.abs(joints[:, 2] - Z0) < 1e-6]
    feet = np.vstack([V[:3, :2], np.array([[x, y] for s in solids for (x, y, _) in _tm(s).vertices])])
    plate = _plate(feet, base_joints, 6.0)
    jig = mf.Manifold.batch_boolean([plate] + solids, mf.OpType.Add)
    jig = jig - mf.Manifold.batch_boolean(cuts, mf.OpType.Add)
    return _tm(jig), rods, joints, dict(base_cradles=sum(h[0] == "base" for h in held), top_posts=len(posts))


def rods_mesh(rods, rod_d: float):
    mf = _mf()
    return _tm(mf.Manifold.batch_boolean([_cyl(a, b, rod_d / 2) for a, b in rods], mf.OpType.Add))


def reference_rods(p: TetrixParams):
    """Full tetrix as cut rods, sitting on z=0 (visualisation only)."""
    tets = subdivide(tetra_vertices(p.edge, p.rod_d / 2), p.level)
    tm = rods_mesh(rods_of(tets, p.joint_allowance), p.rod_d)
    tm.vertices = tm.vertices - [0, 0, tm.bounds[0, 2]]
    return tm, joints_of(tets)


# ----------------------------------------------------------------------------------------- checks
def check(tm) -> dict:
    parts = tm.split(only_watertight=False)
    ext = tm.extents
    return dict(watertight=bool(tm.is_watertight), winding_consistent=bool(tm.is_winding_consistent),
                bodies=len(parts), volume_ml=round(float(tm.volume) / 1000, 3),
                min_z=round(float(tm.bounds[0, 2]), 4),
                size_mm=[round(float(x), 2) for x in ext],
                fits_bed=bool(max(ext[:2]) <= BED_KEEP and ext[2] <= BED_Z),
                triangles=int(len(tm.faces)))


def joint_clearance(jig, joints) -> float:
    import trimesh
    _, dist, _ = trimesh.proximity.closest_point(jig, np.asarray(joints, float))
    inside = jig.contains(np.asarray(joints, float))
    dist = np.where(inside, -dist, dist)
    return float(dist.min())


def rod_interference_mm3(jig, rods, rod_d) -> float:
    return float((_man(jig) ^ _man(rods_mesh(rods, rod_d))).volume())


def liftout_clear(jig, rods, rod_d, travel=120.0, step=5.0) -> bool:
    """Lifting the tied rod piece straight up never touches the jig."""
    mf = _mf()
    J = _man(jig)
    R = _man(rods_mesh(rods, rod_d))
    for z in np.arange(0.0, travel + step, step):
        if (J ^ R.translate((0, 0, float(z)))).volume() > 1e-3:
            return False
    return True


def build(p: TetrixParams):
    """{'gauge','tetra_jig','assembly_<E>'...,'rods_reference'} -> trimesh (print pose, z>=0) + info."""
    d = dims(p)
    out, info = {}, {}
    g, gi = gauge(p); out["rod_length_gauge"] = g; info["rod_length_gauge"] = gi
    tj, trods, tV = tetra_jig(p)
    out["single_tetra_jig"] = tj
    info["single_tetra_jig"] = dict(rods=trods, joints=tV, edge=d.small_edge)
    for s in d.stages:
        aj, arods, ajoints, ai = assembly_plate(p, s)
        k = f"assembly_plate_{s:g}mm"
        out[k] = aj
        info[k] = dict(rods=arods, joints=ajoints, edge=s, **ai)
    rr, rj = reference_rods(p)
    out["rods_reference"] = rr
    info["rods_reference"] = dict(joints=rj)
    return out, info


def verify(p: TetrixParams, out, info) -> dict:
    res = {}
    for k, tm in out.items():
        c = check(tm)
        if k != "rods_reference" and k != "rod_length_gauge":
            i = info[k]
            c["min_jig_to_joint_mm"] = round(joint_clearance(tm, i["joints"]), 2)
            c["rod_interference_mm3"] = round(rod_interference_mm3(tm, i["rods"], p.rod_d), 4)
            c["lifts_out_vertically"] = liftout_clear(tm, i["rods"], p.rod_d)
            for x in ("base_cradles", "top_posts"):
                if x in i:
                    c[x] = i[x]
            c["ok"] = bool(c["watertight"] and c["bodies"] == 1 and c["fits_bed"] and c["rod_interference_mm3"] == 0
                           and c["min_jig_to_joint_mm"] >= MIN_JOINT_CLEAR and c["lifts_out_vertically"]
                           and c.get("top_posts", 3) >= 3)
        elif k == "rod_length_gauge":
            c["ok"] = bool(c["watertight"] and c["bodies"] == 1 and c["fits_bed"])
        res[k] = c
    return res


def stl_bytes(tm) -> bytes:
    return tm.export(file_type="stl")


def dims_dict(p: TetrixParams) -> dict:
    return asdict(dims(p))
