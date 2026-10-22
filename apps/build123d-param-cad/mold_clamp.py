"""Threaded wall clamps for the pour frame (bd_warehouse ISO threads). Units: **mm**.

Optional Mold-master accessory: C-clamps that pull the pour-frame wall down into the locating groove,
so the seam seals without (or with less) hot glue and the frame can't float on the silicone.

Side view of one clamp at the edge of the plate (clamp printed lying on its side, no supports)::

        thumbscrew head ▐██▌
                ┌────────╫────────┬───┐  arm, captive hex nut in a through slot
                │   [ nut ║ slot ] │   │
                └────────╫────────┤   │
                         ║ M10 screw  │ spine
          frame wall  ┃  ▼ presses  │   │
         silicone     ┃ the wall top│   │
        ──────────────┃──┐ groove   │   │
        plate          ╰─┘          │   │
        ────────────────────────────┘   │
          ▀▀▀▀▀▀▀▀▀▀▀▀ jaw (under the plate) ┘

* **Clamp body**: lower jaw hooks under the plate edge, spine outside it, arm over the frame wall.
  The screw axis is over the middle of the wall. Through-slot for a hex nut (printed one or a steel
  DIN 934 nut, same across-flats), teardrop clearance hole (prints horizontally without supports).
* **Nut** and **thumbscrew**: printed separately with the thread axis vertical (head down for the screw),
  ISO metric coarse threads from ``bd_warehouse.thread.IsoThread`` with ``manufacturing_compensation``
  (FDM: external threads shrink inward, internal threads grow outward by that much).
* One clamp size serves master A and master B (their frame tops differ by the plates' thickness
  difference): the screw travel covers both.

Needs the wall to stand **on the plate** (locating groove on, or the "ledge" frame style).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from geometry import TorusParams
from mold import MoldParams, cavity_half, frame_dims, frame_z0, plate_half, plate_thickness_a, plate_thickness_b

# ISO 261 coarse pitch, ISO 4032 / DIN 934 nut across flats and height
ISO_COARSE = {6: (1.0, 10.0, 5.2), 8: (1.25, 13.0, 6.8), 10: (1.5, 17.0, 8.4), 12: (1.75, 19.0, 10.8)}


@dataclass(frozen=True)
class ClampParams:
    size: int = 10                       # M size (ISO coarse): 6, 8, 10, 12
    compensation: float = 0.15           # bd_warehouse manufacturing_compensation per part (FDM)
    count: int = 4                       # clamps per mold (one per side; 8 = two per side)
    width: float = 22.0                  # clamp width (prints as the height on its side)
    jaw: float = 4.0                     # lower jaw thickness (the plate rests on the jaws)
    jaw_reach: float = 14.0              # how far the jaw reaches under the plate
    spine: float = 7.0                   # spine thickness
    edge_gap: float = 0.6                # min gap plate edge -> spine inner face (grows to clear the screw)
    travel_margin: float = 4.0           # arm underside sits this far above the higher (B) frame top
    nut_clearance: float = 0.4           # hex slot oversize (across flats and height)
    head_d: float = 24.0                 # thumbscrew head diameter
    head_h: float = 8.0                  # thumbscrew head height
    tip_d: float = 6.0                   # flat tip pressing on the wall top (capped at the wall thickness)


def thread_spec(c: ClampParams):
    if c.size not in ISO_COARSE:
        raise ValueError(f"M{c.size} not supported: pick one of {sorted(ISO_COARSE)}")
    return ISO_COARSE[c.size]


def validate_clamp(t: TorusParams, m: MoldParams, c: ClampParams) -> None:
    thread_spec(c)
    if not (m.groove or m.frame_style == "ledge"):
        raise ValueError("clamps need the frame wall to stand on the plate: turn the locating groove on "
                         "(or use the 'ledge' frame style)")
    if not 0.0 <= c.compensation <= 0.5:
        raise ValueError("manufacturing compensation must be 0-0.5 mm")
    if c.count not in (4, 8):
        raise ValueError("use 4 or 8 clamps")
    if c.tip_d > c.size:
        raise ValueError("the screw tip must not be wider than the thread")
    _, af, _ = thread_spec(c)
    if af + c.nut_clearance + 2 * 2.0 > c.width + 4:
        raise ValueError("clamp too narrow for the nut")


def frame_top_above_table(t: TorusParams, m: MoldParams, master: str) -> float:
    """Height of the pour-frame top above the table with the frame on master 'A' or 'B'."""
    pt = plate_thickness_a(m) if master == "A" else plate_thickness_b(m)
    return pt + frame_z0(m) + frame_dims(t, m)[2]


def screw_inset(t: TorusParams, m: MoldParams) -> float:
    """Screw axis distance inside the plate edge = over the middle of the frame wall."""
    return plate_half(t, m) - (cavity_half(t, m) + m.wall / 2)


def layout(t: TorusParams, m: MoldParams, c: ClampParams) -> dict:
    """Clamp profile numbers (x outward from the plate edge, z up from the plate bottom)."""
    pitch, af, nut_h = thread_spec(c)
    top_a = frame_top_above_table(t, m, "A")
    top_b = frame_top_above_table(t, m, "B")
    arm_t = max(16.0, nut_h + c.nut_clearance + 2 * 3.0)
    z_arm = max(top_a, top_b) + c.travel_margin          # arm underside
    xs = -screw_inset(t, m)                               # screw axis
    arm_x0 = xs - (af / 2 + c.nut_clearance / 2 + 3.0)    # arm inner end
    x_sp = max(c.edge_gap, xs + c.size / 2 + 1.0)          # spine inner face, clear of the screw
    # screw: from the head down to 1 mm below the lower frame top (presses master A's frame)
    shank = arm_t + (z_arm - min(top_a, top_b)) + 2.0
    return dict(pitch=pitch, af=af, nut_h=nut_h, top_a=top_a, top_b=top_b, arm_t=arm_t, z_arm=z_arm, xs=xs,
                arm_x0=arm_x0, x_sp=x_sp, shank=shank,
                travel=z_arm - min(top_a, top_b), height=c.jaw + z_arm + arm_t)


def clamp_positions(t: TorusParams, m: MoldParams, c: ClampParams):
    """(x, y, angle_deg) of each clamp's plate-edge point, clamp +x pointing outward."""
    ph = plate_half(t, m)
    offs = [0.0] if c.count == 4 else [-ph / 2.2, ph / 2.2]
    out = []
    for ang in (0, 90, 180, 270):
        a = math.radians(ang)
        for o in offs:
            x, y = ph, o
            out.append((x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a), ang))
    return out


# ---- build123d solids ---------------------------------------------------------

def clamp_body(t: TorusParams, m: MoldParams, c: ClampParams):
    """Clamp body in assembly pose: x outward, plate bottom at z = 0, centred on y = 0."""
    from build123d import Align, Box, Cylinder, Location, Pos, Rot, extrude, Plane, RegularPolygon, Polygon
    validate_clamp(t, m, c)
    L = layout(t, m, c)
    W = c.width
    xo = L["x_sp"] + c.spine
    # side profile (XZ), extruded along Y
    pts = [(-c.jaw_reach, -c.jaw), (xo, -c.jaw), (xo, L["z_arm"] + L["arm_t"]),
           (L["arm_x0"], L["z_arm"] + L["arm_t"]), (L["arm_x0"], L["z_arm"]), (L["x_sp"], L["z_arm"]),
           (L["x_sp"], 0.0), (-c.jaw_reach, 0.0)]
    prof = Plane.XZ * Polygon(*pts, align=None)
    body = extrude(prof, amount=W / 2, both=True)
    # teardrop clearance hole along z through the arm, point toward +y (the print "up" on its side)
    r = c.size / 2 + 0.4
    zc = L["z_arm"] + L["arm_t"] / 2
    hole = Pos(L["xs"], 0, zc) * Cylinder(r, L["arm_t"] + 2)
    hole += Pos(L["xs"], r / math.sqrt(2), zc) * Rot(0, 0, 45) * Box(r, r, L["arm_t"] + 2)
    # hex nut slot: through along y, flats facing +-x (no turning), centred in the arm
    hx = (L["af"] + c.nut_clearance) / 2
    nh = L["nut_h"] + c.nut_clearance
    hexp = Plane.XY.offset(zc - nh / 2) * RegularPolygon(hx / math.cos(math.pi / 6), 6, major_radius=True,
                                                        rotation=30)
    nut_prism = extrude(Pos(L["xs"], 0, 0) * hexp, amount=nh)
    # sweep the hex along y: union of the hex prism and the box spanning its x-extent (flats ±hx)
    slot = nut_prism + Pos(L["xs"], 0, zc) * Box(2 * hx, W + 2, nh)
    return body - hole - slot


def nut(c: ClampParams):
    """Printed hex nut, thread axis z, flat on the bed (z = 0..nut_h)."""
    from build123d import Align, Cylinder, Plane, RegularPolygon, extrude, Pos, Cone
    from bd_warehouse.thread import IsoThread
    pitch, af, nut_h = thread_spec(c)
    D = float(c.size)
    # flats facing +-x, same as the clamp's nut slot
    hexp = Plane.XY * RegularPolygon(af / 2 / math.cos(math.pi / 6), 6, major_radius=True, rotation=30)
    body = extrude(hexp, amount=nut_h)
    # internal thread root radius incl. compensation, plus half of bd_warehouse's 0.2 mm
    # interference band so the bore never coincides with the thread root face
    bore = D / 2 + c.compensation + 0.1
    body -= Pos(0, 0, nut_h / 2) * Cylinder(bore, nut_h + 2, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    th = IsoThread(major_diameter=D, pitch=pitch, length=nut_h, external=False,
                   end_finishes=("chamfer", "chamfer"), manufacturing_compensation=c.compensation)
    # countersink both ends (lead-in, and the first layer's elephant foot)
    cs = Cone(bore + 0.8, bore - 0.2, 1.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    out = (body + th).clean()
    out -= cs
    out -= Pos(0, 0, nut_h) * Cone(bore - 0.2, bore + 0.8, 1.0, align=(Align.CENTER, Align.CENTER, Align.MAX))
    return out


def thumbscrew(t: TorusParams, m: MoldParams, c: ClampParams):
    """Thumbscrew printed head down: head z = 0..head_h, threaded shank up to the flat tip."""
    from build123d import Align, Cylinder, Cone, Pos
    from bd_warehouse.thread import IsoThread
    L = layout(t, m, c)
    pitch = L["pitch"]
    D = float(c.size)
    al = (Align.CENTER, Align.CENTER, Align.MIN)
    # 1 mm x 45 deg chamfer on the bottom (bed) edge against elephant's foot
    head = Cone(c.head_d / 2 - 1.0, c.head_d / 2, 1.0, align=al) + Pos(0, 0, 1.0) * Cylinder(
        c.head_d / 2, c.head_h - 1.0, align=al)
    n = 10                                               # finger scallops
    for k in range(n):
        a = 2 * math.pi * k / n
        head -= Pos(c.head_d / 2 * math.cos(a) * 1.08, c.head_d / 2 * math.sin(a) * 1.08, -1) * Cylinder(
            c.head_d * 0.11, c.head_h + 2, align=al)
    th = IsoThread(major_diameter=D, pitch=pitch, length=L["shank"], external=True,
                   end_finishes=("square", "fade"), manufacturing_compensation=c.compensation)
    core = Cylinder(th.min_radius + 0.01, L["shank"], align=al)
    shank = Pos(0, 0, c.head_h) * (core + th)
    # flat tip, chamfered down to tip_d so it doesn't dig into the wall
    tip_len = 1.5
    tip_r = min(c.tip_d, m.wall) / 2                       # never wider than the wall it presses on
    tip = Pos(0, 0, c.head_h + L["shank"]) * Cone(th.min_radius, tip_r, tip_len, align=al)
    return (head + shank + tip).clean()


def parts(t: TorusParams, m: MoldParams, c: ClampParams) -> dict:
    """{'clamp': body (assembly pose), 'nut', 'thumbscrew'} build123d solids."""
    return {"clamp": clamp_body(t, m, c), "nut": nut(c), "thumbscrew": thumbscrew(t, m, c)}


def print_pose(name: str, shape):
    """Clamp on its side (profile flat on the bed), others as built; all sitting on z = 0."""
    from build123d import Pos, Rot
    s = Rot(90, 0, 0) * shape if name == "clamp" else shape
    bb = s.bounding_box()
    return Pos(-(bb.min.X + bb.max.X) / 2, -(bb.min.Y + bb.max.Y) / 2, -bb.min.Z) * s


def to_trimesh(shape, tol: float = 0.02, angular: float = 0.15):
    import numpy as np
    import trimesh
    v, f = shape.tessellate(tol, angular)
    V = np.array([(p.X, p.Y, p.Z) for p in v])
    return trimesh.Trimesh(V, np.array(f), process=True)


def stl_bytes(shape, tol: float = 0.02) -> bytes:
    """STL bytes (mm) via build123d's exporter (watertight per solid)."""
    import os
    import tempfile
    from build123d import export_stl
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "x.stl")
        export_stl(shape, p, tolerance=tol, angular_tolerance=0.15)
        return open(p, "rb").read()


def step_bytes(shape) -> bytes:
    import os
    import tempfile
    from build123d import export_step
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "x.step")
        export_step(shape, p)
        return open(p, "rb").read()


def assembly(t: TorusParams, m: MoldParams, c: ClampParams, master: str = "A", parts_: dict | None = None):
    """[(name, shape)] of every clamp, nut and screw placed on master 'A' or 'B' in the mold's
    coordinates (pour floor z = 0), each screw screwed down until its tip touches the frame top."""
    from build123d import Location, Pos, Rot
    L = layout(t, m, c)
    p = parts_ or parts(t, m, c)
    pt = plate_thickness_a(m) if master == "A" else plate_thickness_b(m)
    top = L["top_a"] if master == "A" else L["top_b"]
    zc = L["z_arm"] + L["arm_t"] / 2
    total = c.head_h + L["shank"] + 1.5
    local = [("clamp", p["clamp"]),
             ("nut", Pos(L["xs"], 0, zc - L["nut_h"] / 2) * p["nut"]),
             ("thumbscrew", Pos(L["xs"], 0, top + total) * Rot(180, 0, 0) * p["thumbscrew"])]
    out = []
    for x, y, ang in clamp_positions(t, m, c):
        loc = Location((x, y, -pt), (0, 0, ang))
        out += [(name, loc * s) for name, s in local]
    return out


def head_clearance(t: TorusParams, m: MoldParams, c: ClampParams, master: str = "A") -> float:
    """Gap between the screw head and the arm top with the tip on the frame (> 0: travel left)."""
    L = layout(t, m, c)
    top = L["top_a"] if master == "A" else L["top_b"]
    return (top + 1.5 + L["shank"]) - (L["z_arm"] + L["arm_t"])
