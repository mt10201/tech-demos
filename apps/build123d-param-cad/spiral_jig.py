"""Spin-to-wind jig for a flat, OPEN-spaced copper-wire spiral (double "S" or single), mm.

Mechanism: a straight wire (twisted copper pair, ~2.0 mm envelope) goes in through the body's two tangent entry
ports, across the winding disc in its diametral start slot, and between two brass dowel pins in the disc hub.
Turning the winged T-handle (keyed into the disc from below through the body floor) rotates the disc; each wire
arm hooks round one pin, then wraps against the OUTSIDE of its own scroll wall, so the spacing between rounds is
set by the walls, not by the wire packing on itself. Rotate the disc counter-clockwise seen from the top
(clockwise seen from below, at the handle). The coil lifts straight out of the open top.

Spiral maths (per arm, polar, s = turning angle from the end of the pin hook):
  even   r_t(s) = r0 + P*s/2pi                          (Archimedean; round-to-round spacing P/arms)
  golden r_t(s) = r0 + P0*(phi**(s/2pi) - 1)/ln(phi)    (pitch grows x1.618 per turn)
r0 = 2a with a = pin_gap/2 + pin_d/2 (the arm leaves its pin on the far side). P / P0 and the end angle are solved
so the arm uses the full wire length and ends at the target outer radius (coil_od/2 - wire/2).

Springback: the RELAXED coil is the target. The jig is drawn at wind curvature k_w = k_t + dk along the arm
(r_wind = 1/(1/r_target + dk)), so after release (k drops by dk) the coil relaxes to the target.
Default dk = 3.4*sy/(E*d) for annealed copper strand (sy 70 MPa, E 117 GPa, d 0.98 mm).

Parts (single watertight bodies, z >= 0, print pose, no supports): body, disc, handle. Pins are bought.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict, replace
from typing import Dict, List, Tuple

import numpy as np

CUBIT = 523.6
PHI = (1 + 5 ** 0.5) / 2
BED_KEEP = 225.0
BED_Z = 200.0
SEG = 96
SIG_Y, E_CU, D_STRAND = 70.0, 117000.0, 0.98
DK_SOFT_CU = 3.4 * SIG_Y / (E_CU * D_STRAND)        # ~0.00208 1/mm
SINGLE_TAIL = 6.0       # single spiral: straight stub held past the pins
GOLDEN_MIN_GAP = 1.5    # below this the centre needs a hand bend
PRESETS = {"1/2 cubit (261.8 mm)": (CUBIT / 2, 46.0), "1/4 cubit (130.9 mm)": (CUBIT / 4, 33.0)}

# Off-the-shelf centre pins (verified listing, Nov 17 2026)
PIN_PART = dict(desc="360 brass dowel pin, 1/8 in dia x 1/2 in long (3.175 x 12.7 mm), +0/+0.0002 in",
                vendor="McMaster-Carr", part="97325A135", pack=25, per_jig=2,
                url="https://www.mcmaster.com/97325A135/",
                alt="3/16 x 1/2 in brass: McMaster 97325A155 (pack of 10)")


@dataclass(frozen=True)
class SpiralParams:
    wire_length: float = CUBIT / 2   # total wire wound into the coil
    coil_od: float = 46.0            # TARGET relaxed coil OD (outer edge of wire)
    spacing: str = "even"            # "even" | "golden"
    arms: int = 2                    # 2 = double (S) spiral, 1 = single (other end anchored at the pins)
    wire_w: float = 2.0              # wire envelope (twisted pair)
    channel: float = 2.3             # channel width: wire seat clearance against its wall (2.2-2.4)
    wall_h: float = 3.0
    wall_t: float = 1.4
    dk: float = DK_SOFT_CU           # springback compensation, 1/mm
    pin_d: float = 3.175
    pin_len: float = 12.7
    pin_gap: float = 2.3             # gap between the two pins (wire threads through)
    pin_protrude: float = 6.0        # above the disc floor
    pin_fit: float = -0.05           # hole dia = pin_d + pin_fit (press fit)
    run_clear: float = 0.3           # per side: disc in body pocket, handle journal in body bore
    key_clear: float = 0.2           # per side: handle drive lugs in disc
    body_margin: float = 12.0        # body OD = coil_od + 2*margin
    handle_span: float = 70.0


DEFAULT = SpiralParams()
DISC_FLOOR_MIN = 3.0
BODY_FLOOR = 4.0
JOURNAL_D = 24.0
LUG_D, LUG_H, LUG_R = 5.0, 4.0, 8.5
HUB_D, HUB_H, WING_H = 30.0, 12.0, 10.0


def preset_params(name: str, **kw) -> SpiralParams:
    L, od = PRESETS[name]
    return SpiralParams(wire_length=L, coil_od=od, **kw)


# ----------------------------------------------------------------------------------------- spiral solve
def _pin_a(p):
    return p.pin_gap / 2 + p.pin_d / 2


def _r_target(p, s, P):
    r0 = 2 * _pin_a(p)
    if p.spacing == "golden":
        return r0 + P * (PHI ** (s / (2 * math.pi)) - 1) / math.log(PHI)
    return r0 + P * s / (2 * math.pi)


def _P_for(p, s_end, R):
    r0 = 2 * _pin_a(p)
    if p.spacing == "golden":
        return (R - r0) * math.log(PHI) / (PHI ** (s_end / (2 * math.pi)) - 1)
    return 2 * math.pi * (R - r0) / s_end


def _spiral_pts(p, s_end, P, n=None):
    n = n or max(200, int(s_end / math.radians(0.5)))
    s = np.linspace(0, s_end, n)
    r = _r_target(p, s, P)
    psi = -math.pi / 2 - s
    return np.column_stack([r * np.cos(psi), r * np.sin(psi)]), s


def _len(pts):
    return float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())


def arm_length(p) -> float:
    return p.wire_length / 2 if p.arms == 2 else p.wire_length - SINGLE_TAIL


def hook_pts(p, n=40):
    a = _pin_a(p)
    t = np.linspace(math.pi / 2, -math.pi / 2, n)
    return np.column_stack([a * np.cos(t), -a + a * np.sin(t)])


@dataclass
class SpiralSolution:
    s_end: float
    P: float                 # even: pitch per arm turn; golden: P0 (innermost pitch)
    target: np.ndarray       # full arm (hook + spiral) target polyline
    wind: np.ndarray         # full arm polyline as drawn on the jig
    n_hook: int


def solve(p: SpiralParams) -> SpiralSolution:
    R = p.coil_od / 2 - p.wire_w / 2
    a = _pin_a(p)
    L_sp = arm_length(p) - math.pi * a
    if R <= 2 * a + 0.5 or L_sp <= (R - 2 * a):
        raise ValueError("coil OD / wire length incompatible (wire too short for this OD, or OD too small)")
    lo, hi = 1e-3, 400.0
    for _ in range(80):
        mid = (lo + hi) / 2
        pts, _ = _spiral_pts(p, mid, _P_for(p, mid, R), 600)
        if _len(pts) < L_sp:
            lo = mid
        else:
            hi = mid
    s_end = (lo + hi) / 2
    P = _P_for(p, s_end, R)
    sp, _ = _spiral_pts(p, s_end, P)
    hk = hook_pts(p)
    target = np.vstack([hk, sp[1:]])
    wind = rebend(target, len(hk) - 1, p.dk)
    return SpiralSolution(s_end, P, target, wind, len(hk) - 1)


def rebend(pts, i0, dk):
    """Same arc length, curvature magnitude changed by +dk (tighter) from vertex i0 on; start pose kept."""
    if dk == 0:
        return pts.copy()
    d = np.diff(pts, axis=0)
    ls = np.linalg.norm(d, axis=1)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    dth = np.diff(th)
    sgn = np.sign(dth)
    sgn[sgn == 0] = -1
    lmid = (ls[:-1] + ls[1:]) / 2
    dth_new = dth.copy()
    dth_new[i0:] = dth[i0:] + sgn[i0:] * dk * lmid[i0:]
    th_new = np.concatenate([[th[0]], th[0] + np.cumsum(dth_new)])
    out = np.vstack([pts[0], pts[0] + np.cumsum(np.column_stack([ls * np.cos(th_new), ls * np.sin(th_new)]), 0)])
    return out


def all_arms(p, arm):
    if p.arms == 1:
        return [arm]
    return [arm, -arm]


def coil_od_of(p, arm) -> float:
    return float(2 * np.linalg.norm(arm, axis=1).max() + p.wire_w)


def calibrate_dk(measured_od: float, jig_wound_od: float, wire_w: float = 2.0) -> float:
    """Material springback from one test coil: dk = 1/R_wound - 1/R_released (outer turn, wire centre radii)."""
    Rw, Rm = jig_wound_od / 2 - wire_w / 2, measured_od / 2 - wire_w / 2
    return 1 / Rw - 1 / Rm


def report(p: SpiralParams, sol: SpiralSolution | None = None) -> dict:
    sol = sol or solve(p)
    n = p.arms
    r_t = lambda s: _r_target(p, s, sol.P)
    step = 2 * math.pi / n
    inner_sp = r_t(step) - r_t(0)
    outer_sp = r_t(sol.s_end) - r_t(sol.s_end - step)
    relaxed_uncomp = rebend(sol.target, sol.n_hook, -p.dk)       # jig drawn at target, released
    relaxed_comp = rebend(sol.wind, sol.n_hook, -p.dk)
    d = dict(
        wire_length_mm=round(p.wire_length, 2), arms=n, arm_length_mm=round(arm_length(p), 2),
        spacing=p.spacing, start_radius_mm=round(2 * _pin_a(p), 3),
        turns_per_arm=round(sol.s_end / (2 * math.pi), 3), turns_per_arm_incl_pin_hook=round(sol.s_end / (2 * math.pi) + 0.5, 3),
        target_relaxed_od_mm=round(p.coil_od, 2),
        wound_od_on_jig_mm=round(coil_od_of(p, sol.wind), 2),
        predicted_relaxed_od_mm=round(coil_od_of(p, relaxed_comp), 2),
        relaxed_od_if_uncompensated_mm=round(coil_od_of(p, relaxed_uncomp), 2),
        dk_per_mm=round(p.dk, 5),
    )
    if p.spacing == "even":
        d.update(pitch_per_arm_turn_mm=round(sol.P, 3), round_spacing_mm=round(sol.P / n, 3),
                 gap_mm=round(sol.P / n - p.wire_w, 3))
    else:
        d.update(pitch_inner_mm=round(sol.P, 3), pitch_outer_mm=round(sol.P * PHI ** (sol.s_end / (2 * math.pi)), 3),
                 round_spacing_inner_mm=round(inner_sp, 3), round_spacing_outer_mm=round(outer_sp, 3),
                 gap_inner_mm=round(inner_sp - p.wire_w, 3), gap_outer_mm=round(outer_sp - p.wire_w, 3))
    gi = inner_sp - p.wire_w
    d["innermost_gap_mm"] = round(gi, 3)
    d["center_hand_bend_needed"] = bool(gi < GOLDEN_MIN_GAP)
    d["rounds_overlap"] = bool(gi < 0)          # wire would sit on itself: more OD or less wire
    return d


# ----------------------------------------------------------------------------------------- 2D layout (shapely)
def _right_normals(pts):
    t = np.gradient(pts, axis=0)
    t /= np.linalg.norm(t, axis=1)[:, None]
    return np.column_stack([t[:, 1], -t[:, 0]])     # right of travel (= toward centre for a clockwise spiral)


def walls_2d(p: SpiralParams, sol: SpiralSolution):
    from shapely.geometry import LineString, Point, box
    from shapely.ops import unary_union
    arms = all_arms(p, sol.wind)
    sp = sol.wind[sol.n_hook:]
    off = p.channel / 2 + p.wall_t / 2
    wl = []
    for sgn in ([1] if p.arms == 1 else [1, -1]):
        q = sgn * sp
        c = q + _right_normals(q) * off
        wl.append(LineString(c).buffer(p.wall_t / 2, cap_style=2, join_style=1))
    walls = unary_union(wl)
    chans = unary_union([LineString(a).buffer(p.channel / 2) for a in arms])
    a = _pin_a(p)
    keep_out = unary_union([Point(0, y).buffer((p.pin_d + p.pin_fit) / 2 + 1.0) for y in (a, -a)])
    R_disc = disc_radius(p, sol)
    slot = box(-R_disc - 5, -p.channel / 2, R_disc + 5, p.channel / 2)
    walls = walls.difference(chans).difference(keep_out).difference(slot)
    walls = walls.buffer(-0.35, join_style=2).buffer(0.35, join_style=2)       # drop slivers
    walls = walls.difference(chans.buffer(0.02)).difference(keep_out)           # re-trim what the opening regrew
    walls = walls.intersection(Point(0, 0).buffer(R_disc - 0.4))
    geoms = [g for g in getattr(walls, "geoms", [walls]) if g.area > 2.0]
    return unary_union(geoms), chans


def disc_radius(p, sol):
    return float(np.linalg.norm(sol.wind, axis=1).max() + p.wire_w / 2 + 2.0)


# ----------------------------------------------------------------------------------------- manifold helpers
def _mf():
    import manifold3d as mf
    return mf


def _cs_from_shapely(geom):
    mf = _mf()
    contours = []
    for g in getattr(geom, "geoms", [geom]):
        if g.is_empty:
            continue
        contours.append(np.asarray(g.exterior.coords)[:-1].tolist())
        for h in g.interiors:
            contours.append(np.asarray(h.coords)[:-1].tolist())
    return mf.CrossSection(contours, mf.FillRule.EvenOdd)


def _cyl(r, h, z0=0.0, x=0.0, y=0.0, seg=SEG):
    return _mf().Manifold.cylinder(h, r, r, seg).translate((x, y, z0))


def _chamfered_cyl(r, h, cb=0.0, ct=0.0, seg=SEG):
    mf = _mf()
    parts = [mf.Manifold.cylinder(1e-3, r - cb, r - cb, seg),
             mf.Manifold.cylinder(max(1e-3, h - cb - ct), r, r, seg).translate((0, 0, cb)),
             mf.Manifold.cylinder(1e-3, r - ct, r - ct, seg).translate((0, 0, h - 1e-3))]
    return mf.Manifold.batch_hull(parts)


def _rounded_slab(cs, h, r_top=3.0, cb=0.8, steps=6):
    """Hull of offset slices: bottom chamfer cb, quarter-round top edge r_top (cs should be convex)."""
    mf = _mf()
    sl = [mf.Manifold.extrude(cs.offset(-cb, mf.JoinType.Round), 1e-3),
          mf.Manifold.extrude(cs, 1e-3).translate((0, 0, cb))]
    for k in range(steps + 1):
        al = k / steps * math.pi / 2
        z = h - r_top + r_top * math.sin(al)
        o = -(r_top - r_top * math.cos(al))
        sl.append(mf.Manifold.extrude(cs.offset(o, mf.JoinType.Round) if o < -1e-6 else cs, 1e-3).translate((0, 0, z - 1e-3)))
    return mf.Manifold.batch_hull(sl)


def _tm(man):
    import trimesh
    mesh = man.to_mesh()
    tm = trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts), process=False)
    tm.merge_vertices()
    if tm.volume < 0:
        tm.invert()
    return tm


# ----------------------------------------------------------------------------------------- parts
def layout(p: SpiralParams, sol: SpiralSolution | None = None) -> dict:
    sol = sol or solve(p)
    Rd = disc_radius(p, sol)
    floor_t = max(DISC_FLOOR_MIN, p.pin_len - p.pin_protrude + 0.8, LUG_H + 2 * p.key_clear + 1.2)
    a = _pin_a(p)
    R_body = p.coil_od / 2 + p.body_margin
    R_pocket = Rd + p.run_clear
    z_disc = BODY_FLOOR + p.run_clear                       # disc rides on the handle journal
    z_floor_top = z_disc + floor_t
    H_body = z_floor_top + p.wall_h + 0.6
    R_body = max(R_body, R_pocket + 6.0)
    return dict(sol=sol, R_disc=Rd, disc_floor=floor_t, pin_a=a, R_body=R_body, R_pocket=R_pocket, z_disc=z_disc,
                z_floor_top=z_floor_top, H_body=H_body, R_bore=JOURNAL_D / 2 + p.run_clear)


def disc(p: SpiralParams, L: dict | None = None):
    mf = _mf()
    L = L or layout(p)
    sol, Rd, ft, a = L["sol"], L["R_disc"], L["disc_floor"], L["pin_a"]
    base = _chamfered_cyl(Rd, ft, cb=0.5, ct=0.6)
    w2d, _ = walls_2d(p, sol)
    walls = mf.Manifold.extrude(_cs_from_shapely(w2d), p.wall_h + 0.01).translate((0, 0, ft - 0.01))
    d = base + walls
    embed = p.pin_len - p.pin_protrude
    rh = (p.pin_d + p.pin_fit) / 2
    for y in (a, -a):
        d = d - _cyl(rh, embed + 1, ft - embed, 0, y, 48)
        d = d - mf.Manifold.cylinder(0.4, rh, rh + 0.4, 48).translate((0, y, ft - 0.39))   # lead-in chamfer
    rl = LUG_D / 2 + p.key_clear
    for x in (LUG_R, -LUG_R):
        d = d - _cyl(rl, LUG_H + 2 * p.key_clear + 1.0, -1.0, x, 0, 48)          # blind drive socket from below
    return _tm(d), w2d


def body(p: SpiralParams, L: dict | None = None):
    mf = _mf()
    L = L or layout(p)
    Rb, H = L["R_body"], L["H_body"]
    shell = _chamfered_cyl(Rb, H, cb=1.0, ct=1.6, seg=160)
    # decorative band: a shallow V-groove ring at 40% height
    zg = 0.4 * H
    ring = mf.Manifold.revolve(mf.CrossSection([[[Rb - 0.8, zg], [Rb + 1, zg - 1.4], [Rb + 1, zg + 1.4]]]), 160)
    shell = shell - ring
    # grip flutes (vertical, between the chamfers), interrupted by the band
    nfl = 18
    for k in range(nfl):
        ang = 2 * math.pi * (k + 0.5) / nfl
        x, y = (Rb + 1.6) * math.cos(ang), (Rb + 1.6) * math.sin(ang)
        fl = mf.Manifold.batch_hull([mf.Manifold.sphere(2.6, 24).translate((x, y, zg + 3.0)),
                                     mf.Manifold.sphere(2.6, 24).translate((x, y, H - 3.4))])
        shell = shell - fl
    # pocket with top lead-in chamfer
    Rp = L["R_pocket"]
    pocket = mf.Manifold.batch_hull([_cyl(Rp, H, BODY_FLOOR), _cyl(Rp + 0.9, 1e-3, H + 0.01)])
    shell = shell - pocket - _cyl(L["R_bore"], BODY_FLOOR + 2, -1)
    shell = shell - mf.Manifold.cylinder(0.6, L["R_bore"] + 0.6, L["R_bore"], SEG).translate((0, 0, -0.001))
    # two flared, open-top entry ports, 180 deg apart on the start-slot axis (x). Each is a rounded fan: the
    # mouth at the pocket wall is on the slot axis so the straight wire passes at the start; the fan sweeps from
    # radial to the TANGENT the wire takes from the outer turn at the end of winding (angle asin(Rc/Rp) from radial).
    zf = L["z_floor_top"]
    Rc = float(np.linalg.norm(L["sol"].wind, axis=1).max())
    psi = math.acos(min(0.98, Rc / Rp))
    tdir = np.array([math.sin(psi), -math.cos(psi)])
    w_in, w_out = p.channel / 2 + 0.25, 2.4
    def capsule(x, y, r):
        return mf.Manifold.batch_hull([mf.Manifold.sphere(r, 32).translate((x, y, zf + r)),
                                       _cyl(r, 1e-3, H + 5, x, y, 32)])
    m = np.array([Rp - 0.8, 0.0])
    reach = Rb - Rp + 5.0
    e_rad = m + np.array([reach, 0.0])
    e_tan = m + tdir * (reach / max(0.3, tdir[0]) if tdir[0] > 0.3 else reach * 1.6)
    e_tan = m + tdir * min(np.linalg.norm(e_tan - m), 2.2 * reach)
    port = mf.Manifold.batch_hull([capsule(*m, w_in), capsule(*e_rad, w_out), capsule(*e_tan, w_out)])
    shell = shell - port - port.rotate((0, 0, 180))
    return _tm(shell), dict(port_mouth_x=float(m[0]), port_fan_deg_from_radial=round(math.degrees(math.pi / 2 - psi), 1))


def handle(p: SpiralParams, L: dict | None = None):
    """Winged T-handle, print pose: wings on the bed, journal + drive lugs up."""
    mf = _mf()
    L = L or layout(p)
    span = p.handle_span
    re = 6.5
    w = []
    for sx in (1, -1):
        cs = mf.CrossSection.batch_hull([mf.CrossSection.circle(9.0, 64),
                                         mf.CrossSection.circle(re, 64).translate((sx * (span / 2 - re), 0))])
        w.append(_rounded_slab(cs, WING_H, r_top=3.2, cb=0.8))
    hub = _rounded_slab(mf.CrossSection.circle(HUB_D / 2, SEG), HUB_H, r_top=2.0, cb=0.8)
    # fillet ring where the wings meet the hub (cone frustum)
    fil = mf.Manifold.cylinder(3.0, HUB_D / 2 + 2.5, HUB_D / 2, SEG).translate((0, 0, WING_H - 1.0))
    jh = BODY_FLOOR + p.run_clear
    journal = mf.Manifold.cylinder(jh, JOURNAL_D / 2, JOURNAL_D / 2, SEG).translate((0, 0, HUB_H - 0.01))
    h = w[0] + w[1] + hub + (fil ^ _cyl(HUB_D / 2 + 2.5, WING_H + 2.0)) + journal
    zt = HUB_H + jh
    for x in (LUG_R, -LUG_R):
        lug = mf.Manifold.batch_hull([_cyl(LUG_D / 2, LUG_H - 0.6, zt - 0.01, x, 0, 48),
                                      _cyl(LUG_D / 2 - 0.6, 1e-3, zt + LUG_H, x, 0, 48)])
        h = h + lug
    return _tm(h)


def pins_mesh(p, L):
    import trimesh
    embed = p.pin_len - p.pin_protrude
    out = []
    for y in (L["pin_a"], -L["pin_a"]):
        c = trimesh.creation.cylinder(radius=p.pin_d / 2, height=p.pin_len, sections=48)
        c.apply_translation((0, y, L["z_floor_top"] - embed + p.pin_len / 2))
        out.append(c)
    return trimesh.util.concatenate(out)


def wire_mesh(p, arms_xy, z, r=None, every=2):
    """Tube along each arm polyline (render only)."""
    import trimesh
    r = r or p.wire_w / 2
    out = []
    for arm in arms_xy:
        pts = np.column_stack([arm[::every], np.full(len(arm[::every]), z)])
        if len(pts) < 2:
            continue
        circ = trimesh.path.polygons.Polygon(
            [(r * math.cos(t), r * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 14, endpoint=False)])
        out.append(trimesh.creation.sweep_polygon(circ, pts))
    return trimesh.util.concatenate(out)


def straight_wire(p, L, length):
    """The wire as inserted: straight along x through the slot, centred on the pins (render only)."""
    import trimesh
    c = trimesh.creation.cylinder(radius=p.wire_w / 2, height=length, sections=24)
    c.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, (0, 1, 0)))
    c.apply_translation((0, 0, L["z_floor_top"] + p.wire_w / 2))
    return c


# ----------------------------------------------------------------------------------------- build + verify
def build(p: SpiralParams):
    L = layout(p)
    d, w2d = disc(p, L)
    b, port = body(p, L)
    h = handle(p, L)
    return dict(body=b, winding_disc=d, handle=h), dict(L=L, walls2d=w2d, port=port)


def check(tm) -> dict:
    parts = tm.split(only_watertight=False)
    ext = tm.extents
    return dict(watertight=bool(tm.is_watertight), winding_consistent=bool(tm.is_winding_consistent),
                bodies=len(parts), volume_ml=round(float(tm.volume) / 1000, 3),
                min_z=round(float(tm.bounds[0, 2]), 4), size_mm=[round(float(x), 2) for x in ext],
                fits_bed=bool(max(ext[:2]) <= BED_KEEP and ext[2] <= BED_Z), triangles=int(len(tm.faces)))


def assembled(p, out, info):
    """Parts placed in assembly coordinates (body bottom at z=0)."""
    L = info["L"]
    d = out["winding_disc"].copy(); d.apply_translation((0, 0, L["z_disc"]))
    h = out["handle"].copy(); h.apply_translation((0, 0, -HUB_H))
    return dict(body=out["body"], winding_disc=d, handle=h, pins=pins_mesh(p, L))


def _ivol(a, b):
    mf = _mf()
    def M(t):
        return mf.Manifold(mf.Mesh(np.asarray(t.vertices, np.float32), np.asarray(t.faces, np.uint32)))
    return float((M(a) ^ M(b)).volume())


def verify(p: SpiralParams, out, info) -> dict:
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union
    L = info["L"]; sol = L["sol"]
    res = {k: check(tm) for k, tm in out.items()}
    for k in res:
        c = res[k]
        c["ok"] = bool(c["watertight"] and c["bodies"] == 1 and c["volume_ml"] > 0 and c["fits_bed"] and c["min_z"] >= -1e-6)
    arms = all_arms(p, sol.wind)
    env = unary_union([LineString(a).buffer(p.wire_w / 2) for a in arms])
    w = info["walls2d"]
    pins = unary_union([Point(0, y).buffer(p.pin_d / 2) for y in (L["pin_a"], -L["pin_a"])])
    min_wall = min(w.distance(Point(*q)) for a in arms for q in a[::3]) if not w.is_empty else 99.0
    min_pin = min(pins.distance(Point(*q)) for a in arms for q in a) - p.wire_w / 2
    A = assembled(p, out, info)
    inter = {f"{x}&{y}": round(_ivol(A[x], A[y]), 4) for x, y in
             (("body", "winding_disc"), ("body", "handle"), ("winding_disc", "handle"), ("pins", "body"), ("pins", "handle"))}
    res["clearance"] = dict(
        wire_envelope_vs_walls_area_mm2=round(float(env.intersection(w).area), 5),
        min_wire_centre_to_wall_mm=round(float(min_wall), 3),
        min_wire_surface_to_pin_mm=round(float(min_pin), 3),
        coil_inside_disc=bool(np.linalg.norm(sol.wind, axis=1).max() + p.wire_w / 2 <= L["R_disc"] - 0.5),
        disc_running_clearance_per_side_mm=round(L["R_pocket"] - L["R_disc"], 3),
        assembly_interference_mm3=inter,
        wall_pieces=len(getattr(w, "geoms", [w])),
    )
    c = res["clearance"]
    c["ok"] = bool(c["wire_envelope_vs_walls_area_mm2"] < 1e-3 and c["min_wire_centre_to_wall_mm"] >= p.wire_w / 2 - 1e-3
                   and c["min_wire_surface_to_pin_mm"] >= -1e-6 and c["coil_inside_disc"]
                   and all(v < 0.05 for v in inter.values()))
    return res


def stl_bytes(tm) -> bytes:
    return tm.export(file_type="stl")


def params_dict(p):
    return asdict(p)
