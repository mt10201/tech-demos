"""build123d B-rep for the Rodin torus: plain torus + 12 swept groove cutters.

OpenCascade can sweep the groove cutters (semicircle, arc or U profile) cleanly, but its boolean
``torus − cutters`` is unreliable for these long helical pipes (it returns
invalid solids / wrong volumes, even with fuzzy tolerance or sectioned tori).
So the STEP export ships the **exact B-rep tool bodies** for the CAD system to
combine:

    body "torus"            – the plain torus (R, r)
    bodies "groove_00.."   – circular-profile sweeps along each groove axis (24 for the photo lattice, 12 otherwise)
    wires  "axis_00.."     – the groove centre-lines (spline, inches)

In SOLIDWORKS: open the STEP → Insert ▸ Features ▸ Combine ▸ Subtract
(main body = torus, bodies to subtract = all groove bodies).  The finished,
already-grooved part is the STL (analytic mesh, see ``torus_mesh.py``).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List, Tuple

from build123d import Circle, Compound, Edge, Plane, Pos, Rectangle, Solid, Wire, export_step

from geometry import TorusParams, all_paths, cutter_radius, path_radius, validate, wall_height


def groove_axes(p: TorusParams, n: int = 61, radius: float | None = None) -> List[Edge]:
    """Splines through the profile-circle centre (or another tube radius)."""
    return [
        Edge.make_spline([tuple(map(float, x)) for x in pts])
        for pts in all_paths(p, n, radius=radius)
    ]


CLEARANCE = 0.05  # how far the U walls extend above the surface (in)


def groove_cutters(p: TorusParams, axes: List[Edge] | None = None) -> List[Solid]:
    """Sweep the groove profile along each axis.

    Semicircle / arc: a circle (orientation-free, Frenet sweep).
    U-groove: circle + rectangle (walls) pointing out of the surface; swept with
    an auxiliary spine (the same groove traced 0.3" further out) so the walls
    stay aligned with the torus normal along the whole wrap.
    """
    rho = cutter_radius(p)
    axes = axes or groove_axes(p)
    h = wall_height(p)
    out = []
    if h <= 1e-9:
        for e in axes:
            profile = Plane(origin=e @ 0, z_dir=e % 0) * Circle(rho)
            out.append(Solid.sweep(profile.face(), Wire([e]), is_frenet=True))
        return out
    aux = groove_axes(p, radius=p.tube_radius + 0.3)
    ext = (p.tube_radius + CLEARANCE) - path_radius(p)  # centre → above surface
    for e, a in zip(axes, aux):
        o = e @ 0
        n = (a @ 0) - o
        plane = Plane(origin=o, x_dir=n, z_dir=e % 0)
        face = (Circle(rho) + Pos(ext / 2, 0) * Rectangle(ext, 2 * rho)).face()
        out.append(Solid.sweep(plane * face, Wire([e]), mode=Wire([a])))
    return out


def build_cad_bodies(p: TorusParams) -> Tuple[Solid, List[Solid], List[Edge]]:
    validate(p)
    torus = Solid.make_torus(p.major_radius, p.tube_radius)
    torus.label = "torus"
    axes = groove_axes(p)
    cutters = groove_cutters(p, axes)
    for i, (c, a) in enumerate(zip(cutters, axes)):
        c.label = f"groove_{i:02d}"
        a.label = f"axis_{i:02d}"
    return torus, cutters, axes


def step_bytes(p: TorusParams) -> bytes:
    torus, cutters, axes = build_cad_bodies(p)
    comp = Compound(children=[torus, *cutters, *axes], label="rodin_torus")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rodin_torus.step"
        export_step(comp, str(path))
        return path.read_bytes()
