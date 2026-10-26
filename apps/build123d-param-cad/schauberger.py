"""Schauberger vortex set: hyperbolic funnel, kudu-horn whorl pipe and converging adapter (mm).

Three separate, mating, printable parts, each built as a direct triangle mesh from stacked
cross-section rings (exact sample points, no splines) and checked watertight / single body:

* **Funnel** - free-surface vortex wall r(t) = a_half / (h0 + t), t = 0..H (default 9450 / (90 + t),
  ID 210 -> 60 over 225 mm), 15 mm vertical freeboard collar at the wide end, short circular land at
  the throat. The wall is offset *outward along the normal*, so the inside curve is exact.
* **Horn** - right-hand helix whose radius and egg section both shrink by 1/phi per turn
  (scale = phi**-turns, continuous). Hugelschaffer egg section, blunt end outboard, pointed end
  toward the helix axis, with a quarter-egg indent groove on the pointed flank that twists with the
  path. Straight 12 mm female egg socket at the mouth, open tip, constant 2 mm wall.
* **Adapter** - circular cup over the funnel land, 20 mm no-twist loft circle -> egg (the only
  circle-to-egg transition, converging), then an undersized egg spigot (0.3 mm total clearance) with
  a chamfered lip that slides into the horn socket. The indent is carried into the spigot so the
  joint is keyed (it can only go in one way round).

Print coordinates: every part's lowest point is z = 0. Funnel wide collar down, horn egg mouth
down (helix axis vertical), adapter cup down.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import trimesh

PHI = (1.0 + math.sqrt(5.0)) / 2.0
BED_MM = (235.0, 235.0, 250.0)       # owner's measured bed (X, Y, usable Z)
ENVELOPE_MM = (225.0, 225.0, 245.0)  # bed minus ~10 mm margin
DENSE = 2048                         # dense boundary samples for exact normal offsets


# ----------------------------------------------------------------------------------------- params
@dataclass(frozen=True)
class FunnelParams:
    a_half: float = 9450.0      # r(t) = a_half / (h0 + t)   (a = 2 * a_half = 18900 mm^2 in d = a / (h0 + t))
    h0: float = 90.0
    H: float = 225.0            # hyperbola height
    collar: float = 15.0        # vertical freeboard collar at the wide end (locked by the owner)
    land: float = 5.0           # circular land at the throat (245 - 225 - 15)
    wall: float = 2.8
    samples: int = 181          # hyperbola samples (exact points on the curve; max sag 0.002 mm)
    segments: int = 200         # around the axis (chord error 0.013 mm at the collar)


@dataclass(frozen=True)
class HornParams:
    R0: float = 65.0            # helix radius at the mouth
    turns: float = 3.0
    height: float = 200.0       # helix rise (constant pitch = height / turns)
    egg_A: float = 54.0         # inner egg major (radial) at the mouth
    egg_ratio: float = PHI      # A / B  ->  B = 54 / phi = 33.37
    egg_w: float = 0.2          # Hugelschaffer asymmetry w / a (0 = ellipse)
    indent: float = 0.25        # indent width as a fraction of A (quarter egg: 54 / 4 = 13.5 mm)
    indent_depth: float = 0.25  # indent depth as a fraction of the indent width (13.5 -> 3.4 mm)
    wall: float = 2.0
    socket: float = 12.0        # straight female egg socket at the mouth
    rings_per_turn: int = 80
    segments: int = 144


@dataclass(frozen=True)
class AdapterParams:
    land_od: float = 65.6       # funnel throat land OD (60 + 2 x 2.8)
    cup_clearance: float = 0.3  # on diameter
    cup_wall: float = 1.9
    cup_len: float = 5.0        # = funnel land length
    throat_id: float = 60.0     # funnel throat ID (adapter bore starts here, no ledge)
    loft: float = 20.0
    spigot: float = 11.0
    spigot_clearance: float = 0.3  # on diameter (0.15 per side) vs the horn socket
    spigot_wall: float = 1.8
    chamfer: float = 0.6
    segments: int = 144


# ---------------------------------------------------------------------------------- mesh helpers
def rings_to_mesh(rings: list[np.ndarray]) -> trimesh.Trimesh:
    """Closed loop of rings (each (M, 3), same angular order) -> watertight genus-1 tube."""
    R = np.asarray(rings, float)
    n, m = R.shape[:2]
    v = R.reshape(-1, 3)
    i = np.arange(n)[:, None]
    j = np.arange(m)[None, :]
    a = i * m + j
    b = i * m + (j + 1) % m
    c = ((i + 1) % n) * m + (j + 1) % m
    d = ((i + 1) % n) * m + j
    f = np.concatenate([np.stack([a, b, c], -1).reshape(-1, 3), np.stack([a, c, d], -1).reshape(-1, 3)])
    mesh = trimesh.Trimesh(v, f, process=True)
    trimesh.repair.fix_normals(mesh)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def drop_to_bed(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    lo = mesh.bounds[0]
    mesh.apply_translation([-(mesh.bounds[0][0] + mesh.bounds[1][0]) / 2,
                            -(mesh.bounds[0][1] + mesh.bounds[1][1]) / 2, -lo[2]])
    return mesh


def check(mesh: trimesh.Trimesh) -> dict:
    """Printability checks for an open pipe: watertight, one body, consistent winding, +volume, genus 1."""
    ext = mesh.extents
    return dict(
        watertight=bool(mesh.is_watertight),
        winding_consistent=bool(mesh.is_winding_consistent),
        is_volume=bool(mesh.is_volume),
        bodies=len(mesh.split(only_watertight=False)),
        euler=int(mesh.euler_number),
        volume_cm3=float(mesh.volume / 1000.0),
        extents=tuple(float(e) for e in ext),
        triangles=len(mesh.faces),
        fits=bool(ext[0] <= ENVELOPE_MM[0] and ext[1] <= ENVELOPE_MM[1] and ext[2] <= ENVELOPE_MM[2]),
    )


def stl_bytes(mesh: trimesh.Trimesh) -> bytes:
    return mesh.export(file_type="stl")


# ----------------------------------------------------------------------------------- 2-D sections
def _angles(m: int) -> np.ndarray:
    return np.linspace(0.0, 2 * np.pi, m, endpoint=False)


def egg_polar(A: float, B: float, w: float, phis: np.ndarray) -> np.ndarray:
    """Hugelschaffer egg, length A along +X (blunt end at +X, pointed end at -X), max breadth B.

    y(x) = b * sqrt((a^2 - x^2) / (a^2 - 2 w x + w^2)), a = A / 2, w = egg_w * a; scaled so the
    widest breadth is exactly B. Returns the polar radius about the major-axis midpoint."""
    a = A / 2.0
    ww = w * a
    t = np.linspace(0.0, 2 * np.pi, 8192, endpoint=False)
    x = a * np.cos(t)
    y = a * np.sin(t) / np.sqrt(a * a - 2 * ww * x + ww * ww)
    y *= (B / 2.0) / np.abs(y).max()
    ang = np.mod(np.arctan2(y, x), 2 * np.pi)
    r = np.hypot(x, y)
    o = np.argsort(ang)
    ang, r = ang[o], r[o]
    return np.interp(np.mod(phis, 2 * np.pi), ang, r, period=2 * np.pi)


def horn_section(p: HornParams, phis: np.ndarray) -> np.ndarray:
    """Inner horn section at scale 1 (mouth): egg with a cosine indent centred on the pointed end."""
    A = p.egg_A
    B = A / p.egg_ratio
    r = egg_polar(A, B, p.egg_w, phis)
    width = p.indent * A
    depth = p.indent_depth * width
    tip = float(egg_polar(A, B, p.egg_w, np.array([np.pi]))[0])
    half = (width / 2.0) / tip                       # angular half-width at the pointed end
    dphi = np.angle(np.exp(1j * (phis - np.pi)))      # wrapped distance from the pointed end
    bump = np.where(np.abs(dphi) < half, 0.5 * (1 + np.cos(np.pi * dphi / half)), 0.0)
    return r - depth * bump


def offset_polar(r: np.ndarray, phis: np.ndarray, dist: float, out_phis: np.ndarray) -> np.ndarray:
    """Exact normal offset (Minkowski sum / erosion with a disk) of a star-shaped closed curve given
    densely in polar form, sampled back on ``out_phis``. dist > 0 grows, dist < 0 shrinks."""
    p = np.stack([r * np.cos(phis), r * np.sin(phis)], -1)              # (K, 2)
    d = np.stack([np.cos(out_phis), np.sin(out_phis)], -1)              # (M, 2)
    pd = d @ p.T                                                        # (M, K) projection on the ray
    h2 = (p * p).sum(1)[None, :] - pd ** 2                              # squared distance to the ray
    T = abs(dist)
    disc = T * T - h2
    ok = disc >= 0
    s = np.sqrt(np.where(ok, disc, 0.0))
    if dist >= 0:
        return np.where(ok & (pd > 0), pd + s, -np.inf).max(1)
    return np.where(ok & (pd > 0), pd - s, np.inf).min(1)


def _ring2d(r: np.ndarray, phis: np.ndarray) -> np.ndarray:
    return np.stack([r * np.cos(phis), r * np.sin(phis)], -1)


# ------------------------------------------------------------------------------------------ funnel
def funnel_profile(p: FunnelParams = FunnelParams()):
    """(inner, outer) (r, z) polylines in print coordinates (wide collar down, z = 0 on the bed).
    Hyperbola parameter t maps to z = collar + t."""
    t = np.linspace(0.0, p.H, p.samples)
    r = p.a_half / (p.h0 + t)
    dr = -p.a_half / (p.h0 + t) ** 2
    nrm = np.stack([np.ones_like(t), -dr], -1) / np.sqrt(1 + dr ** 2)[:, None]   # material side
    z = p.collar + t
    r0, rH = r[0], r[-1]
    ztop = p.collar + p.H + p.land
    inner = [(r0, 0.0)] + list(zip(r, z)) + ([(rH, ztop)] if p.land > 0 else [])
    T = p.wall
    outer = [(r0 + T, 0.0), (r0 + T, p.collar)]
    a1 = math.atan2(nrm[0, 1], nrm[0, 0])
    for a in np.linspace(0, a1, 9)[1:-1]:                       # round outer corner at the collar joint
        outer.append((r0 + T * math.cos(a), p.collar + T * math.sin(a)))
    off = np.stack([r, z], -1) + T * nrm
    keep = off[:, 1] < p.collar + p.H - 1e-6
    outer += [tuple(q) for q in off[keep]]
    outer += [(rH + T, p.collar + p.H)]
    if p.land > 0:
        outer += [(rH + T, ztop)]
    return np.array(inner), np.array(outer)


def build_funnel(p: FunnelParams = FunnelParams()) -> trimesh.Trimesh:
    inner, outer = funnel_profile(p)
    loop = np.concatenate([inner, outer[::-1]])
    ph = _angles(p.segments)
    rings = [np.stack([r * np.cos(ph), r * np.sin(ph), np.full_like(ph, z)], -1) for r, z in loop]
    return rings_to_mesh(rings)


def funnel_step(path, p: FunnelParams = FunnelParams()):
    """Exact-revolve STEP: the same sampled profile polygon revolved 360 deg about Z (OpenCascade)."""
    from build123d import Axis, Polyline, Vector, export_step, make_face, revolve

    inner, outer = funnel_profile(p)
    loop = np.concatenate([inner, outer[::-1]])
    pts = [Vector(float(r), 0.0, float(z)) for r, z in loop]
    solid = revolve(make_face(Polyline(*pts, close=True)), Axis.Z, 360)
    export_step(solid, str(path))
    return solid


# -------------------------------------------------------------------------------------------- horn
def horn_path(p: HornParams, s: np.ndarray):
    """Centre line, tangent and section frame (u = radial/blunt, v = T x u) at s in [0, 1]."""
    N = p.turns
    k = PHI ** (-N * s)
    th = 2 * np.pi * N * s
    R = p.R0 * k
    c = np.stack([R * np.cos(th), R * np.sin(th), p.height * s], -1)
    dR = -R * N * math.log(PHI)
    dth = 2 * np.pi * N
    dc = np.stack([dR * np.cos(th) - R * dth * np.sin(th), dR * np.sin(th) + R * dth * np.cos(th),
                   np.full_like(s, p.height)], -1)
    T = dc / np.linalg.norm(dc, axis=1, keepdims=True)
    rad = np.stack([np.cos(th), np.sin(th), np.zeros_like(th)], -1)
    u = rad - (rad * T).sum(1, keepdims=True) * T
    u /= np.linalg.norm(u, axis=1, keepdims=True)
    v = np.cross(T, u)
    return c, T, u, v, k


def horn_rings(p: HornParams = HornParams()):
    """Inner and outer 3-D rings from the socket entrance to the tip (unplaced helix coordinates)."""
    n = max(int(round(p.rings_per_turn * p.turns)), 8) + 1
    s = np.linspace(0.0, 1.0, n)
    c, T, u, v, k = horn_path(p, s)
    ph = _angles(p.segments)
    dense = _angles(DENSE)
    rin_d = horn_section(p, dense)
    rin = horn_section(p, ph)
    inner, outer = [], []

    def place(ci, ui, vi, xy):
        return ci + xy[:, :1] * ui + xy[:, 1:] * vi

    # straight socket: one extra ring a socket-length back along -T at the mouth frame (scale 1)
    pre = [c[0] - T[0] * p.socket] if p.socket > 0 else []
    rout0 = offset_polar(rin_d, dense, p.wall, ph)
    for cc in pre:
        inner.append(place(cc, u[0], v[0], _ring2d(rin, ph)))
        outer.append(place(cc, u[0], v[0], _ring2d(rout0, ph)))
    for i in range(n):
        ro = offset_polar(rin_d * k[i], dense, p.wall, ph)
        inner.append(place(c[i], u[i], v[i], _ring2d(rin * k[i], ph)))
        outer.append(place(c[i], u[i], v[i], _ring2d(ro, ph)))
    return inner, outer


def build_horn_raw(p: HornParams = HornParams()) -> trimesh.Trimesh:
    inner, outer = horn_rings(p)
    return rings_to_mesh(inner + outer[::-1])


def build_horn(p: HornParams = HornParams()) -> trimesh.Trimesh:
    """Horn in print position: helix axis vertical, egg mouth (large end) down on the bed."""
    return drop_to_bed(build_horn_raw(p))


def horn_dims(p: HornParams = HornParams()) -> dict:
    A, B = p.egg_A, p.egg_A / p.egg_ratio
    ke = PHI ** (-p.turns)
    w = p.indent * A
    return dict(mouth_A=A, mouth_B=B, tip_A=A * ke, tip_B=B * ke, R_end=p.R0 * ke,
                pitch=p.height / p.turns, indent_width=w, indent_depth=w * p.indent_depth,
                tip_indent_width=w * ke, tip_indent_depth=w * p.indent_depth * ke,
                mouth_area_cm2=_area(horn_section(p, _angles(DENSE))) / 100.0,
                tip_area_cm2=_area(horn_section(p, _angles(DENSE)) * ke) / 100.0,
                helix_angle_deg=math.degrees(math.atan2(p.height / p.turns, 2 * math.pi * p.R0)))


def _area(r: np.ndarray) -> float:
    return float(0.5 * np.sum(r ** 2) * (2 * np.pi / len(r)))


# ----------------------------------------------------------------------------------------- adapter
def adapter_rings(a: AdapterParams = AdapterParams(), h: HornParams = HornParams()):
    """(z, r_inner(phi), r_outer(phi)) stations; egg major along +x (blunt end +x), indent at -x."""
    ph = _angles(a.segments)
    dense = _angles(DENSE)
    horn_in = horn_section(h, dense)                                # horn socket bore (scale 1)
    s_out = offset_polar(horn_in, dense, -a.spigot_clearance / 2, ph)
    s_out_d = offset_polar(horn_in, dense, -a.spigot_clearance / 2, dense)
    s_in = offset_polar(s_out_d, dense, -a.spigot_wall, ph)
    s_cham = offset_polar(s_out_d, dense, -a.chamfer, ph)
    cup_r = (a.land_od + a.cup_clearance) / 2
    ro_cup = cup_r + a.cup_wall
    r_th = a.throat_id / 2
    one = np.ones_like(ph)
    ins, outs = [], []
    ins += [(0.0, cup_r * one), (a.cup_len, cup_r * one)]             # cup bore, then stop shoulder
    z0 = a.cup_len
    nl = 24
    for q in np.linspace(0, 1, nl + 1):                               # no-twist loft, radial blend per angle
        ins.append((z0 + a.loft * q, (1 - q) * r_th + q * s_in))
    z1 = z0 + a.loft
    z2 = z1 + a.spigot
    ins.append((z2, s_in))
    outs.append((0.0, ro_cup * one))
    outs.append((z0, ro_cup * one))
    for q in np.linspace(0, 1, nl + 1)[1:]:
        r_in_q = (1 - q) * r_th + q * s_in
        rin_dense = np.interp(dense, ph, r_in_q, period=2 * np.pi)
        wall_ok = offset_polar(rin_dense, dense, a.spigot_wall, ph)
        blend = (1 - q) * ro_cup + q * s_out
        outs.append((z0 + a.loft * q, np.maximum(blend, wall_ok) if q < 1 else s_out))
    outs.append((z2 - a.chamfer, s_out))
    outs.append((z2, s_cham))
    egg_d = egg_polar(h.egg_A, h.egg_A / h.egg_ratio, h.egg_w, dense)    # egg without the indent
    e_out = offset_polar(egg_d, dense, -a.spigot_clearance / 2, ph)
    e_in = offset_polar(np.interp(dense, ph, e_out, period=2 * np.pi), dense, -a.spigot_wall, ph)
    return ph, ins, outs, dict(cup_id=2 * cup_r, cup_od=2 * ro_cup, length=z2,
                               cup_len=a.cup_len, loft=a.loft, spigot_len=a.spigot,
                               spigot_egg_out_A=float(e_out[0] + e_out[len(ph) // 2]),
                               spigot_egg_out_B=float(2 * np.max(e_out * np.abs(np.sin(ph)))),
                               spigot_egg_in_A=float(e_in[0] + e_in[len(ph) // 2]),
                               spigot_egg_in_B=float(2 * np.max(e_in * np.abs(np.sin(ph)))),
                               ledge_into_horn=float((h.egg_A - (e_in[0] + e_in[len(ph) // 2])) / 2),
                               spigot_out_A=float(s_out[0] + s_out[len(ph) // 2]),
                               spigot_out_B=float(2 * np.max(s_out * np.abs(np.sin(ph)))),
                               spigot_in_A=float(s_in[0] + s_in[len(ph) // 2]),
                               spigot_in_B=float(2 * np.max(s_in * np.abs(np.sin(ph)))))


def build_adapter(a: AdapterParams = AdapterParams(), h: HornParams = HornParams()) -> trimesh.Trimesh:
    ph, ins, outs, _ = adapter_rings(a, h)
    loop = ins + outs[::-1]
    rings = [np.stack([r * np.cos(ph), r * np.sin(ph), np.full_like(ph, z)], -1) for z, r in loop]
    return rings_to_mesh(rings)


def adapter_dims(a: AdapterParams = AdapterParams(), h: HornParams = HornParams()) -> dict:
    return adapter_rings(a, h)[3]


# ---------------------------------------------------------------------------------------- assembly
def assembly(fp: FunnelParams = FunnelParams(), hp: HornParams = HornParams(),
             ap: AdapterParams = AdapterParams()):
    """Mated set in use position (funnel wide end up). Funnel land end face sits on the adapter
    shoulder (world z = 0); the adapter spigot points down into the horn socket; the horn mouth axis
    is aligned with the adapter axis and the egg/indent orientation matches (keyed joint)."""
    f = build_funnel(fp)
    ztop = fp.collar + fp.H + fp.land
    f.apply_transform(_flip(ztop))                                 # land at the bottom, z in [0, ztop]
    a = build_adapter(ap, hp)
    a.apply_transform(_flip(ap.cup_len))                          # shoulder at z = 0, spigot downward
    z_mouth = -ap.loft                                             # spigot root = socket entrance
    hm = build_horn_raw(hp)
    c, T, u, v, _ = horn_path(hp, np.array([0.0]))
    entrance = c[0] - T[0] * hp.socket
    Rm = np.stack([u[0], v[0], T[0]])                              # rows: horn local -> (x, y, axis)
    world = np.diag([1.0, -1.0, -1.0]) @ Rm                        # u -> +x, v -> -y, T -> -z
    M = np.eye(4)
    M[:3, :3] = world
    M[:3, 3] = np.array([0, 0, z_mouth]) - world @ entrance
    hm.apply_transform(M)
    return f, a, hm


def _flip(z_shift: float) -> np.ndarray:
    M = np.diag([1.0, -1.0, -1.0, 1.0])                            # 180 deg about x (a rotation)
    M[2, 3] = z_shift
    return M


def build_all(fp=FunnelParams(), hp=HornParams(), ap=AdapterParams()):
    return dict(Schauberger_Funnel=build_funnel(fp), Schauberger_Horn=build_horn(hp),
                Schauberger_Adapter=build_adapter(ap, hp))


def horn_clearance(p: HornParams = HornParams()) -> dict:
    """Self-intersection guards for the swept pipe.

    * ``min_advance``: every outer-section vertex moves forward along the path tangent from one ring
      to the next (> 0 means neighbouring sections never cross, even at the tightening tip).
    * ``min_turn_gap``: closest approach (mm) between outer-wall vertices of rings that are more
      about one turn apart along the path (> 0 means no turn touches another)."""
    from scipy.spatial.distance import cdist

    inner, outer = horn_rings(p)
    O = np.asarray(outer)
    n0 = 1 if p.socket > 0 else 0
    n = max(int(round(p.rings_per_turn * p.turns)), 8) + 1
    s = np.linspace(0.0, 1.0, n)
    _, T, _, _, _ = horn_path(p, s)
    adv = np.einsum("imk,ik->im", O[n0 + 1:] - O[n0:-1], T[:-1])
    per = int(p.rings_per_turn)
    gap = np.inf
    for i in range(len(O)):           # the closest approach between turns is ~one turn apart
        for j in range(i + per - per // 4, min(i + per + per // 4, len(O))):
            gap = min(gap, float(cdist(O[i], O[j]).min()))
    return dict(min_advance=float(adv.min()), min_turn_gap=gap)
