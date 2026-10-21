"""Real-scan moai head: "Quarry Moai - Rapa Nui/Easter Island" by Ryan Shackleton (CC BY 4.0), modified.

The processed mold master lives in assets/ (built by scripts/build_moai_head_scan.py from the
original Sketchfab OBJ, which is not in the repo). This module only loads and scales it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Tuple

import numpy as np

ASSETS = Path(__file__).resolve().parent / "assets"
SCAN_STL = ASSETS / "moai_head_scan_152mm.stl"
SCAN_PREVIEW = ASSETS / "moai_head_scan_preview.ply"
SCAN_HEIGHT_MM = 152.4  # height of the committed STL

TITLE = "Quarry Moai - Rapa Nui/Easter Island"
AUTHOR = "Ryan Shackleton"
URL = "https://sketchfab.com/3d-models/quarry-moai-rapa-nuieaster-island-dd6027d79fe14549ab7b2eae0d94de5d"
LICENSE = "CC BY 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
CHANGES = (
    "Modified: re-oriented upright; cropped to the head at the chin; soil/hillside removed; flat base added; "
    "the uncaptured back (hillside contact) replaced by a sculpted rounded back of head and neck with a "
    "weathered-stone texture (the face is the unchanged scan); gaps under ~1.5 mm, nostrils and scan holes closed "
    "(voxel rebuild at 0.3 mm), made watertight and genus 0; decimated; scaled to 152.4 mm."
)
ATTRIBUTION = (
    f'"{TITLE}" by {AUTHOR} ({URL}), licensed under {LICENSE} ({LICENSE_URL}). {CHANGES}'
)


@lru_cache(maxsize=2)
def _load(path: str) -> Tuple[np.ndarray, np.ndarray]:
    import trimesh

    m = trimesh.load(path, process=True)
    return np.asarray(m.vertices, float), np.asarray(m.faces, np.int64)


def head_mesh(height_mm: float = SCAN_HEIGHT_MM, preview: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    """Head mesh in mm, flat base on z = 0, centred in x/y, scaled to height_mm."""
    v, f = _load(str(SCAN_PREVIEW if preview else SCAN_STL))
    v = v - [0.5 * (v[:, 0].max() + v[:, 0].min()), 0.5 * (v[:, 1].max() + v[:, 1].min()), v[:, 2].min()]
    return v * (height_mm / np.ptp(v[:, 2])), f


def stl_bytes(height_mm: float = SCAN_HEIGHT_MM) -> bytes:
    if abs(height_mm - SCAN_HEIGHT_MM) < 1e-9:
        return SCAN_STL.read_bytes()
    import trimesh

    v, f = head_mesh(height_mm)
    return trimesh.Trimesh(v, f, process=False).export(file_type="stl")


def file_name(height_mm: float) -> str:
    return f"moai_head_scan_{height_mm:.0f}mm.stl"
