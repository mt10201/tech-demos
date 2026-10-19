"""Generate a standalone build123d Python snippet from TorusParams."""

from __future__ import annotations

from geometry import PHI, TorusParams, cutter_radius, path_radius, sweeps


def generate_snippet(p: TorusParams) -> str:
    top, bottom = sweeps(p)
    return f'''from build123d import *
import math

# Units: inches   φ = {PHI:.10f}
R, r      = {p.major_radius:.4f}, {p.tube_radius:.4f}   # major / tube radius
DEPTH     = {p.groove_depth:.4f}             # groove depth
CUT_R     = {cutter_radius(p):.4f}             # groove profile radius (= depth → semicircle)
RP        = {path_radius(p):.4f}             # cutter axis tube-radius = r - DEPTH + CUT_R
N, HAND   = {p.n_grooves}, {p.handedness}
TOP, BOT  = {top:.6f}, {bottom:.6f}   # azimuth swept on top / bottom half (rad)
ROT       = math.radians({p.rotation_deg:.4f})
QMIN, QMAX = R - RP, R + RP

def wrap(i, n=121):
    """One full wrap; top half is a golden spiral seen from above."""
    pts = []
    for j in range(n):
        th = 2 * math.pi * j / (n - 1)
        q = R + RP * math.cos(th)
        s = math.log(QMAX / q) / math.log(QMAX / QMIN)       # 0 outer → 1 inner
        dphi = s * TOP if th <= math.pi else TOP + (1 - s) * BOT
        ph = ROT + i * 2 * math.pi / N + HAND * dphi
        pts.append((q * math.cos(ph), q * math.sin(ph), RP * math.sin(th)))
    return Edge.make_spline(pts)

torus = Solid.make_torus(R, r)
cutters = []
for i in range(N):
    path = wrap(i)
    profile = Plane(origin=path @ 0, z_dir=path % 0) * Circle(CUT_R)
    cutters.append(Solid.sweep(profile.face(), Wire([path]), is_frenet=True))

# OpenCascade's torus.cut(*cutters) is unreliable for these long helical pipes,
# so export the exact bodies and Combine ▸ Subtract them in SOLIDWORKS:
export_step(Compound(children=[torus, *cutters]), "rodin_torus.step")
# The app's STL (finished grooved part) comes from an analytic mesh: torus_mesh.py
'''
