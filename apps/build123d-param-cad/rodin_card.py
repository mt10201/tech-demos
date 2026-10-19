"""build123d solid for the Rodin coil card."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Tuple

from build123d import (
    Axis,
    BuildPart,
    BuildSketch,
    Circle,
    Location,
    Mode,
    Rectangle,
    export_step,
    export_stl,
    extrude,
    fillet,
)

from geometry import CardParams, groove_specs


def build_rodin_coil_card(params: CardParams):
    """Return a build123d Part: disk minus 12 radial grooves."""
    specs = groove_specs(params)
    depth = min(params.groove_depth, params.thickness)
    # Slot length along radial direction; add tiny overlap so boolean cleans.
    eps = 0.05

    with BuildPart() as part:
        with BuildSketch():
            Circle(radius=params.diameter / 2.0)
        extrude(amount=params.thickness)

        for g in specs:
            length = g.span + 2 * eps
            mid_r = 0.5 * (g.r_start + g.r_end)
            # Local sketch on XY, then place: translate to mid_r along X, rotate about Z.
            angle_rad = math.radians(g.angle_deg)
            loc = Location(
                (
                    mid_r * math.cos(angle_rad),
                    mid_r * math.sin(angle_rad),
                    params.thickness - depth,
                ),
                (0, 0, g.angle_deg),
            )
            with BuildSketch(loc):
                # Rectangle centered; long axis along local +X (= radial after rotation).
                Rectangle(length, params.groove_width)
            extrude(amount=depth + eps, mode=Mode.SUBTRACT)

        if params.rim_fillet > 0:
            # Fillet top/bottom circular edges of the outer cylinder.
            try:
                z_edges = [
                    e
                    for e in part.edges()
                    if abs(e.length - math.pi * params.diameter) < 1.0
                ]
                if z_edges:
                    fillet(z_edges, params.rim_fillet)
            except Exception:
                # Fillet can fail on tiny radii; keep unfilleted solid.
                pass

    return part.part


def tessellate_mesh(part, linear_deflection: float = 0.35) -> Tuple:
    """
    Return (vertices Nx3, faces Mx3) numpy arrays for Plotly Mesh3d.
    """
    import numpy as np

    # build123d Part.tessellate returns list of vectors + triangles
    verts, tris = part.tessellate(linear_deflection)
    vertices = np.array([[v.X, v.Y, v.Z] for v in verts], dtype=float)
    faces = np.array(tris, dtype=int)
    return vertices, faces


def export_files(part, dest_dir: Path | None = None) -> Tuple[Path, Path]:
    """Write STL and STEP; return paths."""
    dest = Path(dest_dir) if dest_dir else Path(tempfile.mkdtemp(prefix="rodin_card_"))
    dest.mkdir(parents=True, exist_ok=True)
    stl_path = dest / "rodin_coil_card.stl"
    step_path = dest / "rodin_coil_card.step"
    export_stl(part, str(stl_path))
    export_step(part, str(step_path))
    return stl_path, step_path
