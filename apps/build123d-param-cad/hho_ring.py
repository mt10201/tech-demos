"""HHO vortex nozzle ring: 4 straight-shank brass tips swirled and tilted DOWN into a tornado below the ring (mm).

SAFETY: the printed PLA part is a COLD-GAS TEST FIXTURE ONLY (aim, swirl, flow balance with air/inert gas).
Never light it. HHO is premixed H2/O2: a flashback into a plastic chamber can burst it, and PLA softens at ~60 C.
The working head must be metal (machined brass / cast bronze from the STEP), fed through a flashback arrestor
and check valve at the tube inlet.

Frame: ring axis = +Z, ring held horizontal, flame BELOW (-Z). Printed as modelled: bottom face (z=0) on the bed,
barb pointing up. No supports: plenum, distribution channel and inlet runner are 45-deg teardrops (point up),
tilted feeds are teardrops pointing up, the inner bore is a downward-opening cone (overhang = tilt <= 45 deg),
barb catch faces are 45-deg chamfers, risers and barb bore are vertical.

Gas path ("split" manifold, default): barb -> vertical bore -> radial runner -> 180-deg distribution arc (upper)
-> two risers at +-90 deg -> full-ring plenum (lower) -> 4 feeds at 45/135/225/315 deg -> stop shoulder -> tip.
Every inlet->tip path is the mirror/rotation image of the others, so lengths are identical.
"direct": barb runner straight into the plenum at 0 deg (paths 45 vs 135 deg of arc) for comparison.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace

import numpy as np

SAFETY = ("COLD-GAS TEST FIXTURE ONLY — never light a printed ring. HHO is premixed hydrogen + oxygen: a flashback "
          "into a plastic chamber can burst it, and PLA softens at about 60 °C. Test aim, swirl and flow balance with "
          "air or an inert gas only. Make the working head in metal (machined brass or cast bronze from the STEP) and "
          "fit a flashback arrestor plus a check valve at the tube inlet.")

# ---------------------------------------------------------------------------------------------- tip catalogue
# shank OD / bore from the listing; "verified" says where each number comes from.
TIPS = {
    "ks8125": dict(name='K&S 8125 round brass tube 1/16" OD x 0.014" wall x 12" (3 pcs)', vendor="K&S Precision Metals",
                   url="https://ksmetals.com/products/br014-1-16", price_usd=5.99, pack="3 x 12 in (≈ 45 tips of 20 mm)",
                   od=1.5875, orifice=0.864, cut_len=20.0,
                   verified="OD 1/16 in and wall 0.014 in from the K&S listing; ID = OD - 2 x wall = 0.034 in (0.864 mm)."),
    "ks8126": dict(name='K&S 8126 round brass tube 3/32" OD x 0.014" wall x 12" (3 pcs)', vendor="K&S Precision Metals",
                   url="https://ksmetals.com/products/br014-3-32", price_usd=6.99, pack="3 x 12 in",
                   od=2.381, orifice=1.676, cut_len=20.0,
                   verified="OD 3/32 in and wall 0.014 in from the listing (ID 0.066 in per Hobbylinc). Bigger flame; "
                            "the 1/16 in tube telescopes inside it as a reducer."),
    "hydroflux18": dict(name="Hydroflux water-torch needle tip, 18 gauge (green)", vendor="Otto Frei (part 114.502)",
                        url="https://www.ottofrei.com/products/hydroflux-torch-tips-18-30-gauge", price_usd=0.95,
                        pack="each (8-gauge kit 114.510 $6.75)", od=1.270, orifice=0.84, cut_len=None,
                        verified="Listing gives gauge only. 18 G cannula OD 1.27 mm / ~0.84 mm ID is the ISO 9626 "
                                 "standard, NOT measured; the hub/fitting is unverified — measure before printing."),
}
PRIMARY_TIP = "ks8125"

BARBS = {  # vinyl tube ID -> barb root OD, crest OD, bore (bore keeps >= 2 mm barb wall at the root)
    '1/4" (6.35 mm) ID': dict(tube_id=6.35, root=6.0, crest=7.2, bore=2.0),
    '5/16" (7.94 mm) ID': dict(tube_id=7.94, root=7.5, crest=8.9, bore=2.6),
}
MANIFOLDS = {"split": "Split manifold (equal paths, default)", "direct": "Direct (single feed into plenum)"}
BED = 235.0
MIN_WALL = 2.0


def _al():
    from build123d import Align
    return (Align.CENTER, Align.CENTER, Align.MIN), None


_CCM, _NONE = _al()


@dataclass(frozen=True)
class RingParams:
    tip: str = PRIMARY_TIP
    shank_od: float = TIPS[PRIMARY_TIP]["od"]
    interference: float = 0.15     # per side: socket bore = shank_od - 2*interference (heat-set)
    insert_depth: float = 5.0      # tip insertion depth to the stop shoulder (along the tip axis)
    lead_in: float = 0.4           # chamfer at the socket mouth
    protrusion: float = 3.0        # recommended tip stick-out past the socket mouth (for jet maths)
    swirl_deg: float = 12.0        # tangential offset of each tip axis (vortex)
    tilt_deg: float = 30.0         # DOWNWARD tilt below horizontal (flame below the ring)
    n_tips: int = 4
    plenum_r: float = 2.0          # plenum teardrop circle radius (lower full ring)
    dist_r: float = 1.6            # distribution arc / inlet runner teardrop radius
    riser_r: float = 1.2
    feed_d: float = 1.0            # feed hole (tilted teardrop) circle diameter, < socket bore = shoulder
    R_plenum: float = 17.0         # plenum centre radius
    wall: float = 2.2              # design wall round the gas channels (>= MIN_WALL)
    z_mouth: float = 2.6           # height of the socket-mouth centre above the bottom face
    tube: str = '1/4" (6.35 mm) ID'
    manifold: str = "split"
    n_barbs: int = 3


DEFAULT = RingParams()


def for_tip(key: str, **kw) -> RingParams:
    return replace(DEFAULT, tip=key, shank_od=TIPS[key]["od"], **kw)


# ---------------------------------------------------------------------------------------------- layout maths
def _unit(v):
    v = np.asarray(v, float); return v / np.linalg.norm(v)


def tip_axis(p: RingParams, k: int) -> np.ndarray:
    """Jet direction of tip k: inward, swirled by swirl_deg (CCW from above), tilted tilt_deg below horizontal."""
    th = math.radians(45.0 + 360.0 / p.n_tips * k if p.n_tips == 4 else 360.0 / p.n_tips * (k + 0.5))
    inward = np.array([-math.cos(th), -math.sin(th), 0.0])
    tang = np.array([-math.sin(th), math.cos(th), 0.0])
    s, t = math.radians(p.swirl_deg), math.radians(p.tilt_deg)
    h = math.cos(s) * inward + math.sin(s) * tang
    return _unit(np.array([h[0] * math.cos(t), h[1] * math.cos(t), -math.sin(t)]))


def tip_angle(p, k):
    return 45.0 + 360.0 / p.n_tips * k if p.n_tips == 4 else 360.0 / p.n_tips * (k + 0.5)


def layout(p: RingParams) -> dict:
    if p.manifold not in MANIFOLDS:
        raise ValueError(f"manifold must be one of {list(MANIFOLDS)}")
    if not (10.0 <= p.tilt_deg <= 45.0):
        raise ValueError("Downward tilt must be 10–45° (above 45° the inner cone overhang needs supports).")
    if not (0.0 <= p.swirl_deg <= 30.0):
        raise ValueError("Swirl must be 0–30°.")
    bore = p.shank_od - 2 * p.interference
    if p.feed_d >= bore - 0.2:
        raise ValueError("Feed hole must be at least 0.2 mm smaller than the socket bore so the tip has a stop shoulder.")
    b = BARBS[p.tube]
    t = math.radians(p.tilt_deg)
    feed_len = p.plenum_r + 1.6                                # plenum centre -> stop shoulder
    L_axis = feed_len + p.insert_depth                         # plenum centre -> mouth, along the axis
    z_p = p.z_mouth + L_axis * math.sin(t)                     # plenum centre height
    if z_p - p.plenum_r < p.wall:
        raise ValueError("Plenum too close to the bottom face — raise z_mouth or the tilt.")
    tear = math.sqrt(2.0)
    if p.manifold == "split":
        z_d = z_p + p.plenum_r * tear + p.wall + p.dist_r      # distribution arc centre (stacked above plenum)
        z_top_gas = z_d + p.dist_r * tear
    else:
        z_d = z_p
        z_top_gas = z_p + p.plenum_r * tear
    H = round(z_top_gas + p.wall, 3)
    R_out = p.R_plenum + max(p.plenum_r, p.dist_r) + p.wall + 0.3
    mouths, tips, dirs, starts = [], [], [], []
    for k in range(p.n_tips):
        th = math.radians(tip_angle(p, k))
        P0 = np.array([p.R_plenum * math.cos(th), p.R_plenum * math.sin(th), z_p])
        d = tip_axis(p, k)
        E = P0 + L_axis * d
        starts.append(P0); dirs.append(d); mouths.append(E); tips.append(E + p.protrusion * d)
    r_mouth = float(np.hypot(*mouths[0][:2]))
    # inner surface: cone widening downward (normal = tilt below horizontal) through the mouths, cylinder above
    r_bot = r_mouth + p.z_mouth * math.tan(t)
    z_cone_top = p.z_mouth + 2.4
    r_cyl = r_mouth - 2.4 * math.tan(t)
    R_barb = R_out + b["crest"] / 2 + 3.0
    boss_r = b["crest"] / 2 + 2.0
    return dict(bore=bore, feed_len=feed_len, L_axis=L_axis, z_p=z_p, z_d=z_d, H=H, R_out=R_out, r_mouth=r_mouth,
                r_bot=r_bot, z_cone_top=z_cone_top, r_cyl=r_cyl, R_barb=R_barb, boss_r=boss_r, barb=b,
                starts=starts, dirs=dirs, mouths=mouths, tips=tips)


def barb_profile(p: RingParams, L: dict):
    """(r, z) points of the upward barb above the boss top: neck, then n barbs (45-deg catch, 1:4 ramp)."""
    b = L["barb"]; r0, r1 = b["root"] / 2, b["crest"] / 2
    z = L["H"]; pts = [(r0, z)]
    z += 2.0; pts.append((r0, z))
    for _ in range(p.n_barbs):
        z += (r1 - r0); pts.append((r1, z))            # 45-deg catch face (printable)
        z += 3.2; pts.append((r0, z))                  # ramp narrowing upward (tube slides on from the top)
    z += 1.2; pts.append((r0, z))
    return pts


def jets(p: RingParams, L: dict | None = None) -> dict:
    """Where the 4 jets go: they are skew lines tangent to a vortex core circle at a common depth."""
    L = L or layout(p)
    T, d = L["tips"][0], L["dirs"][0]
    lam = -(T[0] * d[0] + T[1] * d[1]) / (d[0] ** 2 + d[1] ** 2)      # closest approach to the Z axis
    Q = T + lam * d
    return dict(tip_exit_radius_mm=round(float(np.hypot(*T[:2])), 3), tip_exit_z_mm=round(float(T[2]), 3),
                focal_z_mm=round(float(Q[2]), 3), focal_depth_below_ring_mm=round(float(-Q[2]), 3),
                vortex_core_radius_mm=round(float(np.hypot(*Q[:2])), 3), jet_length_to_focus_mm=round(float(lam), 3))


def path_lengths(p: RingParams, L: dict | None = None) -> dict:
    """Centre-line length barb top -> each socket shoulder (mm)."""
    L = L or layout(p)
    barb_top = barb_profile(p, L)[-1][1]
    common = (barb_top - L["z_d"]) + (L["R_barb"] - p.R_plenum)
    out = {}
    for k in range(p.n_tips):
        a = tip_angle(p, k) % 360.0
        a = a if a <= 180 else 360 - a                        # angular distance from the inlet at 0 deg
        if p.manifold == "split":
            arc = p.R_plenum * (math.radians(90.0) + math.radians(abs(90.0 - a)))
            rise = L["z_d"] - L["z_p"]
        else:
            arc, rise = p.R_plenum * math.radians(a), 0.0
        out[f"tip{k + 1}@{tip_angle(p, k):g}deg"] = round(common + arc + rise + L["feed_len"], 3)
    v = list(out.values())
    return dict(paths_mm=out, max_minus_min_mm=round(max(v) - min(v), 4), spread_pct=round(100 * (max(v) - min(v)) / min(v), 3))


def areas(p: RingParams, L: dict | None = None) -> dict:
    L = L or layout(p)
    tear = lambda r: math.pi * r * r * 0.75 + r * r          # 45-deg teardrop: 3/4 circle + kite
    tips = p.n_tips * math.pi * (TIPS[p.tip]["orifice"] if p.tip in TIPS else p.shank_od * 0.5) ** 2 / 4
    feeds = p.n_tips * tear(p.feed_d / 2)
    return dict(plenum_mm2=round(tear(p.plenum_r), 3), distribution_mm2=round(tear(p.dist_r), 3),
                riser_mm2=round(math.pi * p.riser_r ** 2, 3), barb_bore_mm2=round(math.pi * L["barb"]["bore"] ** 2 / 4, 3),
                feeds_total_mm2=round(feeds, 3), tip_orifices_total_mm2=round(tips, 3),
                plenum_to_tips_ratio=round(tear(p.plenum_r) / tips, 2))


# ---------------------------------------------------------------------------------------------- build123d solids
def _teardrop_face(plane, r):
    from build123d import Circle, Polygon, Pos
    c = math.cos(math.pi / 4) * r
    circ = plane * Circle(r)
    kite = plane * Polygon((c, c), (0, r * math.sqrt(2)), (-c, c), (0, 0), align=_NONE)
    return (circ + kite).faces()[0] if len((circ + kite).faces()) == 1 else (circ + kite)


def _teardrop_ball(center, r):
    """Sphere with a 45-deg cone cap: printable end of a teardrop channel."""
    from build123d import Cone, Pos, Sphere
    c = r / math.sqrt(2)
    return Pos(*center) * Sphere(r) + Pos(center[0], center[1], center[2] + c) * Cone(c, 0, r * math.sqrt(2) - c,
                                                                                           align=_NONE)


def _revolve_teardrop(R, z, r, deg=360.0, start=0.0):
    from build123d import Axis, Plane, Rot, revolve
    f = _teardrop_face(Plane.XZ.offset(0).shift_origin((R, 0, z)), r)
    s = revolve(f, Axis.Z, deg)
    return Rot(0, 0, start) * s if start else s


def _along(P0, d, length, r, tear=True):
    """Channel of radius r from P0 along unit d (teardrop pointing up if tear)."""
    from build123d import Plane, extrude, Circle
    d = _unit(d); up = np.array([0, 0, 1.0]) - d[2] * d
    if np.linalg.norm(up) < 1e-6 or not tear:
        x = np.cross(d, [1, 0, 0]) if abs(d[0]) < 0.9 else np.cross(d, [0, 1, 0])
        pl = Plane(origin=tuple(P0), x_dir=tuple(_unit(x)), z_dir=tuple(d))
        return extrude(pl * Circle(r), length)
    up = _unit(up)
    pl = Plane(origin=tuple(P0), x_dir=tuple(np.cross(up, d)), z_dir=tuple(d))
    return extrude(_teardrop_face(pl, r), length)


def _cyl_along(P0, d, length, r):
    from build123d import Cylinder, Plane, Location
    d = _unit(d)
    x = np.cross(d, [0, 0, 1.0]); x = _unit(x) if np.linalg.norm(x) > 1e-6 else np.array([1.0, 0, 0])
    pl = Plane(origin=tuple(P0), x_dir=tuple(x), z_dir=tuple(d))
    return pl * Cylinder(r, length, align=_NONE)


def _cone_along(P0, d, r0, r1, length):
    from build123d import Cone, Plane
    d = _unit(d)
    x = np.cross(d, [0, 0, 1.0]); x = _unit(x) if np.linalg.norm(x) > 1e-6 else np.array([1.0, 0, 0])
    return Plane(origin=tuple(P0), x_dir=tuple(x), z_dir=tuple(d)) * Cone(r0, r1, length, align=_NONE)


def blank(p: RingParams, L: dict):
    """Solid ring + inlet boss + barb, before any gas path is cut."""
    from build123d import Axis, Box, Cylinder, Plane, Polygon, Pos, revolve
    H = L["H"]; ch = 0.8
    prof = [(L["r_bot"], 0), (L["R_out"] - 0.4, 0), (L["R_out"], 0.4), (L["R_out"], H - ch), (L["R_out"] - ch, H),
            (L["r_cyl"], H), (L["r_cyl"], L["z_cone_top"])]
    ring = revolve(Plane.XZ * Polygon(*prof, align=_NONE), Axis.Z, 360)
    Rb, br = L["R_barb"], L["boss_r"]
    boss = Pos(Rb, 0, 0) * Cylinder(br, H, align=_CCM) + \
        Pos((L["R_out"] - 1.0 + Rb) / 2, 0, 0) * Box(Rb - L["R_out"] + 1.0, 2 * br, H, align=_CCM)
    barb = Pos(Rb, 0, 0) * revolve(Plane.XZ * Polygon((0, L["H"] - 0.01), *barb_profile(p, L),
                                                      (0, barb_profile(p, L)[-1][1]), align=_NONE), Axis.Z, 360)
    return ring + boss + barb


def cavity(p: RingParams, L: dict):
    """Every gas passage (and the tip sockets) as one solid — the negative of the part."""
    from build123d import Cylinder, Pos, Rot
    Rp, zp, zd, Rb = p.R_plenum, L["z_p"], L["z_d"], L["R_barb"]
    top = barb_profile(p, L)[-1][1]
    parts = [_revolve_teardrop(Rp, zp, p.plenum_r)]
    if p.manifold == "split":
        ext = math.degrees((p.riser_r + 0.4) / Rp)            # run past each riser; flat vertical end = printable
        parts.append(_revolve_teardrop(Rp, zd, p.dist_r, 180.0 + 2 * ext, -90.0 - ext))
        for a in (90.0, -90.0):
            c = (Rp * math.cos(math.radians(a)), Rp * math.sin(math.radians(a)))
            parts.append(Pos(c[0], c[1], zp) * Cylinder(p.riser_r, zd - zp, align=_CCM))
    # radial runner from just past the barb axis to the distribution arc (or plenum): teardrop, flat vertical end
    x0 = Rb + L["barb"]["bore"] / 2 + 0.4
    parts.append(_along((x0, 0, zd), (-1, 0, 0), x0 - Rp, p.dist_r))
    parts.append(Pos(Rb, 0, zd) * Cylinder(L["barb"]["bore"] / 2, top - zd + 1.0, align=_CCM))
    for P0, d, E in zip(L["starts"], L["dirs"], L["mouths"]):
        parts.append(_along(P0, d, L["feed_len"] + 0.05, p.feed_d / 2))
        sh = P0 + L["feed_len"] * d
        parts.append(_cyl_along(sh, d, p.insert_depth + 4.0, L["bore"] / 2))
        parts.append(_cone_along(E - p.lead_in * d, d, L["bore"] / 2, L["bore"] / 2 + p.lead_in + 1.5, p.lead_in + 1.5))
    out = parts[0]
    for s in parts[1:]:
        out = out + s
    return out


def build(p: RingParams = DEFAULT):
    L = layout(p)
    B = blank(p, L)
    C = cavity(p, L)
    ring = B - C
    return dict(ring=ring, blank=B, cavity=C, L=L)


# ---------------------------------------------------------------------------------------------- meshes & checks
def stl_bytes(shape, tol=0.01, ang=0.1) -> bytes:
    """STL bytes (mm) via build123d's exporter (shared edges -> watertight per solid)."""
    import os, tempfile
    from build123d import export_stl
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "x.stl")
        export_stl(shape, f, tolerance=tol, angular_tolerance=ang)
        return open(f, "rb").read()


def step_bytes(shape) -> bytes:
    import os, tempfile
    from build123d import Unit, export_step
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "x.step")
        export_step(shape, f, unit=Unit.MM)
        return open(f, "rb").read()


def to_mesh(shape, tol=0.01, ang=0.1):
    import io, trimesh
    m = trimesh.load(io.BytesIO(stl_bytes(shape, tol, ang)), file_type="stl")
    m.merge_vertices()
    return m


def export(res, folder, stem="hho_vortex_ring"):
    from build123d import Unit, export_step, export_stl
    from pathlib import Path
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    stl, step = folder / f"{stem}.stl", folder / f"{stem}.step"
    export_stl(res["ring"], str(stl), tolerance=0.01, angular_tolerance=0.1)
    export_step(res["ring"], str(step), unit=Unit.MM)
    return stl, step


def _gas_samples(p, L, n=60):
    """Points on the gas-channel walls (not the sockets / barb mouth), for the min-wall check."""
    pts = []
    Rp, zp, zd = p.R_plenum, L["z_p"], L["z_d"]
    def ring_pts(R, z, r, a0, a1):
        for a in np.linspace(a0, a1, n):
            for b in np.linspace(0, 2 * math.pi, 24, endpoint=False):
                rr = r * (math.sqrt(2) if abs(b - math.pi / 2) < 1e-9 else 1.0)
                pts.append((math.cos(a) * (R + rr * math.cos(b)), math.sin(a) * (R + rr * math.cos(b)), z + rr * math.sin(b)))
    ring_pts(Rp, zp, p.plenum_r, 0, 2 * math.pi)
    if p.manifold == "split":
        ring_pts(Rp, zd, p.dist_r, -math.pi / 2, math.pi / 2)
    for x in np.linspace(Rp, L["R_barb"], 20):
        for b in np.linspace(0, 2 * math.pi, 24, endpoint=False):
            pts.append((x, p.dist_r * math.cos(b), zd + p.dist_r * math.sin(b)))
    return np.array(pts)


def verify(p: RingParams, res) -> dict:
    import trimesh
    L = res["L"]
    ring, cav, bl = to_mesh(res["ring"]), to_mesh(res["cavity"]), to_mesh(res["blank"])
    parts = ring.split(only_watertight=False)
    cparts = cav.split(only_watertight=False)
    ext = ring.extents
    # connectivity: the single cavity body must contain the barb mouth and every socket mouth
    top = barb_profile(p, L)[-1][1]
    probes = [(L["R_barb"], 0.0, top - 0.5)] + [tuple(E - 1.0 * d) for E, d in zip(L["mouths"], L["dirs"])] + \
             [tuple(P0) for P0 in L["starts"]]
    inside = cav.contains(np.array(probes))
    solid_at = ring.contains(np.array(probes))
    # cavity must breach the blank only at the barb mouth and the sockets
    gas = _gas_samples(p, L)
    pq = trimesh.proximity.ProximityQuery(bl)
    wall = float(np.min(np.abs(pq.signed_distance(gas))))
    nb = len(res["ring"].solids())
    walls = design_walls(p, L)
    out = dict(watertight=bool(ring.is_watertight), winding_consistent=bool(ring.is_winding_consistent),
               mesh_bodies=len(parts), brep_solids=nb, volume_mm3=round(float(ring.volume), 2),
               brep_volume_mm3=round(float(res["ring"].volume), 2),
               gas_cavity_bodies=len(cparts), gas_cavity_volume_mm3=round(float(res["cavity"].volume), 2),
               cavity_reaches_inlet_and_4_sockets=bool(inside.all()), probes_are_open_air=bool(not solid_at.any()),
               min_gas_wall_mm=round(wall, 3), design_walls_mm=walls, size_mm=[round(float(x), 2) for x in ext],
               min_z=round(float(ring.bounds[0, 2]), 4), fits_bed=bool(max(ext[:2]) < BED - 20), triangles=int(len(ring.faces)))
    out["ok"] = bool(out["watertight"] and out["mesh_bodies"] == 1 and nb == 1 and out["gas_cavity_bodies"] == 1
                     and out["cavity_reaches_inlet_and_4_sockets"] and out["probes_are_open_air"]
                     and out["min_gas_wall_mm"] >= MIN_WALL - 0.05
                     and min(walls.values()) >= MIN_WALL - 1e-6 and out["fits_bed"] and abs(out["min_z"]) < 1e-3)
    return out


def design_walls(p: RingParams, L: dict | None = None) -> dict:
    """Analytic minimum walls between gas passages and the outside / each other (mm)."""
    L = L or layout(p); t2 = math.sqrt(2)
    t = math.radians(p.tilt_deg)
    r_in_at_plenum = L["r_mouth"] - (L["z_p"] - p.z_mouth) * math.tan(t)
    w = dict(plenum_to_bottom=round(L["z_p"] - p.plenum_r, 3),
             plenum_to_outer=round(L["R_out"] - p.R_plenum - p.plenum_r, 3),
             plenum_to_inner_bore=round(p.R_plenum - p.plenum_r - max(r_in_at_plenum, L["r_cyl"]), 3),
             gas_to_top=round(L["H"] - (L["z_d"] + (p.dist_r if p.manifold == "split" else p.plenum_r) * t2), 3),
             barb_wall=round((L["barb"]["root"] - L["barb"]["bore"]) / 2, 3),
             runner_to_boss_side=round(L["boss_r"] - p.dist_r, 3))
    if p.manifold == "split":
        w["plenum_to_distribution"] = round(L["z_d"] - p.dist_r - (L["z_p"] + p.plenum_r * t2), 3)
        w["distribution_to_outer"] = round(L["R_out"] - p.R_plenum - p.dist_r, 3)
    return w


def tip_meshes(p: RingParams, L: dict | None = None):
    """Brass tube tips seated at the shoulder, sticking out by `protrusion` (for renders / the app)."""
    import trimesh
    L = L or layout(p); out = []
    for P0, d, T in zip(L["starts"], L["dirs"], L["tips"]):
        a = P0 + L["feed_len"] * d
        out.append(trimesh.creation.cylinder(radius=p.shank_od / 2, segment=[a, T], sections=24))
    return trimesh.util.concatenate(out)


def jet_lines(p: RingParams, L: dict | None = None, extra: float = 6.0):
    """Each jet from its tip exit to `extra` mm past the vortex-core depth: list of (2,3) arrays."""
    L = L or layout(p); j = jets(p, L)
    return [np.array([T, T + (j["jet_length_to_focus_mm"] + extra) * d]) for T, d in zip(L["tips"], L["dirs"])]


def jet_meshes(p: RingParams, L: dict | None = None, r=0.35, extra=6.0):
    import trimesh
    return trimesh.util.concatenate([trimesh.creation.cylinder(radius=r, segment=ln, sections=12)
                                     for ln in jet_lines(p, L, extra)])


def report(p: RingParams) -> dict:
    L = layout(p)
    return dict(socket_bore_mm=round(L["bore"], 4), insert_depth_mm=p.insert_depth, feed_d_mm=p.feed_d,
                ring_od_mm=round(2 * L["R_out"], 2), ring_height_mm=L["H"], mouth_radius_mm=round(L["r_mouth"], 3),
                inner_bottom_d_mm=round(2 * L["r_bot"], 2), inner_top_d_mm=round(2 * L["r_cyl"], 2),
                barb=dict(tube=p.tube, **L["barb"]), walls=design_walls(p, L), jets=jets(p, L), path_balance=path_lengths(p, L), areas=areas(p, L),
                tilt_deg_down=p.tilt_deg, swirl_deg=p.swirl_deg, manifold=p.manifold)


def params_dict(p):
    return asdict(p)
