"""Moai v2 hi-res master (152.4 mm) with integral tooling base + detachable pour frame.

Rebuilt from the original "Quarry Moai - Rapa Nui/Easter Island" scan by Ryan Shackleton (CC BY 4.0) at a
0.25 mm voxel by scripts/build_moai_v2.py. The straight ear/crown lines of the original/v1 were the soil
contact of the half-buried quarry statue (where the scan ends); v2 replaces the planar cut + ear-wide slab
with a 3.5 mm signed-distance morph from the scan into a rounded back (see ATTRIBUTION.md).
Tooling: moai_mold.build_tooling (tower v3 seating, 0.25 mm/side, unchanged). Supersedes v1.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

import moai_mold

ASSETS = Path(__file__).resolve().parent / "assets"
STATUE_STL = ASSETS / "moai_v2_hires_152mm.stl"
PREVIEW = ASSETS / "moai_v2_hires_preview.ply"
HEIGHT_MM = 152.4
FILES = {
    "statue": "moai_v2_hires_152mm.stl",
    "master": "moai_v2_master_with_base.stl",
    "pour_frame": "moai_v2_pour_frame.stl",
}


@lru_cache(maxsize=1)
def statue():
    import trimesh

    m = trimesh.load(STATUE_STL, process=True)
    assert abs(float(m.extents[2]) - HEIGHT_MM) < 0.05
    return m


def preview_mesh() -> Tuple[np.ndarray, np.ndarray]:
    import trimesh

    m = trimesh.load(PREVIEW, process=False)
    return np.asarray(m.vertices, float), np.asarray(m.faces, np.int64)


def dims():
    return moai_mold.dims_for(statue(), facet_safe=True)


@lru_cache(maxsize=1)
def parts() -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    return moai_mold.build_tooling(statue(), facet_safe=True)


def stl_bytes(part: str) -> bytes:
    if part == "statue":
        return STATUE_STL.read_bytes()
    import trimesh

    v, f = parts()[part]
    return trimesh.Trimesh(v, f, process=False).export(file_type="stl")
