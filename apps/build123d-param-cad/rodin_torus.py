"""build123d B-rep for the Rodin torus: plain torus + 12 swept groove cutters.

OpenCascade can sweep the groove cutters (semicircle, arc or U profile) cleanly, but its boolean
``torus − cutters`` is unreliable for these long helical pipes (it returns
invalid solids / wrong volumes, even with fuzzy tolerance or sectioned tori).
So the STEP export ships the **exact B-rep tool bodies** for the CAD system to
combine:

    body "torus"            – the plain torus (R, r)
    bodies "groove_00.."   – circular-profile sweeps along each groove axis (24 for the photo lattice, 12 otherwise)
    wires  "axis_00.."     – the groove centre-lines (spline)

Geometry is built in inches and scaled ×25.4 on export, so every STEP is
written in **millimetres** (unit MM in the file header) at true size.

In SOLIDWORKS: open the STEP → Insert ▸ Features ▸ Combine ▸ Subtract
(main body = torus, bodies to subtract = all groove bodies).  The finished,
already-grooved part is the STL (analytic mesh, see ``torus_mesh.py``).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List, Tuple

from build123d import Circle, Compound, Edge, Plane, Pos, Rectangle, Solid, Unit, Wire, export_step

from geometry import MM_PER_IN, TorusParams, all_paths, cutter_radius, path_radius, validate, wall_height


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


def _step_mm(shape, name: str) -> bytes:
    """Scale an inch-unit shape to mm and write it as a mm STEP.

    ``Compound.scale`` does not rescale ``children`` (which export_step writes
    as the assembly), so each child is scaled and the compound rebuilt."""

    def sc(x):
        y = x.scale(MM_PER_IN)
        y.label = x.label
        return y

    kids = list(getattr(shape, "children", ()) or ())
    shape = Compound(children=[sc(k) for k in kids], label=shape.label) if kids else sc(shape)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / name
        export_step(shape, str(path), unit=Unit.MM)
        return path.read_bytes()


def step_bytes(p: TorusParams) -> bytes:
    torus, cutters, axes = build_cad_bodies(p)
    comp = Compound(children=[torus, *cutters, *axes], label="rodin_torus")
    return _step_mm(comp, "rodin_torus_mm.step")


# ---- finished solid (torus with grooves already subtracted) -----------------

FUZZY_STEPS = (1e-4, 1e-3)


def _occ_cut(base, tool, fuzzy: float):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.collections import List_TopoDS_Shape

    op = BRepAlgoAPI_Cut()
    a, b = List_TopoDS_Shape(), List_TopoDS_Shape()
    a.Append(base.wrapped)
    b.Append(tool.wrapped)
    op.SetArguments(a)
    op.SetTools(b)
    op.SetFuzzyValue(fuzzy)
    op.SetRunParallel(True)
    op.Build()
    if not op.IsDone():
        return None
    shp = op.Shape()
    return Solid(shp) if shp.ShapeType().name == "TopAbs_SOLID" else Compound(shp)


def finished_solid(p: TorusParams, progress=None):
    """Exact B-rep of torus − all U-groove cutters (for a SOLIDWORKS-ready STEP).

    A single multi-tool cut, or cutting a pre-fused tool, gives invalid or
    wrong-volume results in OpenCascade for these long helical cutters.
    Subtracting **one cutter at a time with a fuzzy tolerance (1e-4")** stays
    valid. Each step is checked with BRepCheck, and a failed step is retried
    at 1e-3". This takes minutes, so the app runs it only on demand.
    """
    torus, cutters, _ = build_cad_bodies(p)
    res = torus
    for k, c in enumerate(cutters):
        nxt = None
        for fz in FUZZY_STEPS:
            nxt = _occ_cut(res, c, fz)
            if nxt is not None and nxt.is_valid and nxt.volume < res.volume:
                break
            nxt = None
        if nxt is None:
            raise RuntimeError(f"OpenCascade boolean failed at groove {k}")
        res = nxt
        if progress:
            progress(k + 1, len(cutters))
    res.label = "rodin_torus_grooved"
    return res


def finished_step_bytes(p: TorusParams, progress=None) -> bytes:
    return _step_mm(finished_solid(p, progress), "rodin_torus_grooved_mm.step")
