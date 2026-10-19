"""build123d B-rep for the Rodin torus: plain torus + 12 swept groove cutters.

OpenCascade can sweep the 12 semicircle cutters cleanly, but its boolean
``torus − cutters`` is unreliable for these long helical pipes (it returns
invalid solids / wrong volumes, even with fuzzy tolerance or sectioned tori).
So the STEP export ships the **exact B-rep tool bodies** for the CAD system to
combine:

    body "torus"            – the plain torus (R, r)
    bodies "groove_00..11"  – circular-profile sweeps along each groove axis
    wires  "axis_00..11"    – the groove centre-lines (spline, inches)

In SOLIDWORKS: open the STEP → Insert ▸ Features ▸ Combine ▸ Subtract
(main body = torus, bodies to subtract = the 12 grooves).  The finished,
already-grooved part is the STL (analytic mesh, see ``torus_mesh.py``).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List, Tuple

from build123d import Circle, Compound, Edge, Plane, Solid, Wire, export_step

from geometry import TorusParams, all_paths, cutter_radius, validate


def groove_axes(p: TorusParams, n: int = 61) -> List[Edge]:
    return [Edge.make_spline([tuple(map(float, x)) for x in pts]) for pts in all_paths(p, n)]


def groove_cutters(p: TorusParams, axes: List[Edge] | None = None) -> List[Solid]:
    rho = cutter_radius(p)
    out = []
    for e in axes or groove_axes(p):
        profile = Plane(origin=e @ 0, z_dir=e % 0) * Circle(rho)
        out.append(Solid.sweep(profile.face(), Wire([e]), is_frenet=True))
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
