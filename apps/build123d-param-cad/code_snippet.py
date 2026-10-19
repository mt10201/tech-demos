"""Generate a standalone build123d Python snippet from TorusParams."""

from __future__ import annotations


from geometry import PHI, TorusParams, cutter_radius, families, path_radius, sweeps


def generate_snippet(p: TorusParams) -> str:
    top, bottom = sweeps(p)
    fams = families(p)
    if p.pattern == "photo":
        dphi_code = "    return th * SWEEP / math.pi        # constant pitch: SWEEP rim → hole"
        consts = f"SWEEP = math.radians({p.sweep_deg:.4f})   # azimuth travelled rim → hole"
    else:
        dphi_code = (
            "    q = R + RP * math.cos(th)\n"
            "    s = math.log(QMAX / q) / math.log(QMAX / QMIN)   # 0 rim → 1 hole\n"
            "    return s * TOP if th <= math.pi else TOP + (1 - s) * BOT   # front = golden spiral"
        )
        consts = f"TOP, BOT = {top:.6f}, {bottom:.6f}   # front / back sweep (rad)"
    return f'''from build123d import *

# Pattern: {p.pattern}    Units: inches    φ = {PHI:.10f}
R, r      = {p.major_radius:.4f}, {p.tube_radius:.4f}   # major / tube radius
DEPTH     = {p.groove_depth:.4f}             # groove depth
CUT_R     = {cutter_radius(p):.4f}             # groove profile radius (= depth → semicircle)
RP        = {path_radius(p):.4f}             # cutter axis tube-radius = r - DEPTH + CUT_R
N         = {p.n_grooves}                    # grooves per direction
DIRS      = {fams}                # +1 / -1 rotational directions
ROT       = math.radians({p.rotation_deg:.4f})
{consts}
QMIN, QMAX = R - RP, R + RP

def dphi(th):
    """Azimuth travelled at tube angle th (0 = rim, pi = hole)."""
{dphi_code}

def wrap(i, d, n=121):
    pts = []
    for j in range(n):
        th = 2 * math.pi * j / (n - 1)
        q = R + RP * math.cos(th)
        ph = ROT + i * 2 * math.pi / N + d * dphi(th)
        pts.append((q * math.cos(ph), q * math.sin(ph), RP * math.sin(th)))
    return Edge.make_spline(pts)

torus = Solid.make_torus(R, r)
cutters = []
for d in DIRS:
    for i in range(N):
        path = wrap(i, d)
        profile = Plane(origin=path @ 0, z_dir=path % 0) * Circle(CUT_R)
        cutters.append(Solid.sweep(profile.face(), Wire([path]), is_frenet=True))

# OpenCascade's torus.cut(*cutters) is unreliable for these long helical pipes,
# so export the exact bodies and Combine ▸ Subtract them in SOLIDWORKS:
export_step(Compound(children=[torus, *cutters]), "rodin_torus.step")
# The app's STL (finished grooved part) comes from an analytic mesh: torus_mesh.py
'''
