"""Moai mold v1: original preserved, blend localized, tower-v3 seating exact, watertight parts."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
import trimesh

import moai_mold
import moai_scan

ORIG = Path(moai_scan.__file__).parent / "assets" / "moai_head_scan_152mm.stl"
BLEND = moai_mold.BLEND_STL
ORIG_SHA = "f2c214d8b9b32f2502e5f73ba2bfe0563575c28f25a9a0ee2cd065e2ecd8494a"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def test_original_asset_bytes_unchanged():
    assert ORIG.is_file() and _sha(ORIG) == ORIG_SHA


def test_blend_exists_watertight_genus0_same_height():
    m = trimesh.load(BLEND, process=True)
    assert m.is_watertight and m.is_winding_consistent and m.euler_number == 2
    assert len(m.split(only_watertight=False)) == 1
    assert m.extents[2] == pytest.approx(152.4, abs=0.05)
    assert m.bounds[0][2] == pytest.approx(0.0, abs=1e-3)


def test_blend_face_region_matches_original_closely():
    """Protected face should be essentially unchanged (NN displacement tiny)."""
    from scipy.spatial import cKDTree

    o = trimesh.load(ORIG, process=True)
    b = trimesh.load(BLEND, process=True)
    # hard face sample
    vo = o.vertices
    face = (vo[:, 1] < -1.0) & (np.abs(vo[:, 0]) < 18.0) & (vo[:, 2] > 20) & (vo[:, 2] < 145)
    d, _ = cKDTree(b.vertices).query(vo[face], k=1)
    assert float(d.max()) < 0.25
    assert float(np.percentile(d, 99)) < 0.15


def test_mold_dims_match_tower_v3_constants():
    d = moai_mold.dims_for()
    assert d.clearance_per_side == pytest.approx(0.25)
    assert d.wall == pytest.approx(3.0)
    assert d.groove_depth == pytest.approx(1.6)
    assert d.groove_width == pytest.approx(3.5)  # 3 + 2*0.25
    assert d.silicone_side_mm == pytest.approx(10.0, abs=0.05)
    assert d.top_cover_mm == pytest.approx(6.0)
    assert d.plate_t == pytest.approx(4.0)
    assert d.frame_id == pytest.approx(2 * (d.max_r_mm + 10.0), abs=1e-6)
    assert d.silicone_ml > 500  # ~1 L class for this head


def test_build_parts_master_and_frame():
    parts = moai_mold.build_parts()
    d = moai_mold.dims_for()
    mv, mf = parts["master"]
    fv, ff = parts["pour_frame"]
    master = trimesh.Trimesh(mv, mf, process=True)
    frame = trimesh.Trimesh(fv, ff, process=True)
    assert master.is_watertight and master.euler_number == 2
    assert len(master.split(only_watertight=False)) == 1
    assert master.extents[0] == pytest.approx(d.plate_d, abs=0.05)
    assert frame.is_watertight
    assert frame.extents[0] == pytest.approx(d.frame_od, abs=0.05)
    assert frame.extents[2] == pytest.approx(d.frame_len, abs=0.05)
    # Frame seats: ID matches dims
    # groove clearance identity
    assert abs((d.frame_gr_out - d.frame_gr_in) - (d.wall + 2 * d.clearance_per_side)) < 1e-9


def test_stl_download_names():
    assert moai_mold.file_name("statue").endswith("v1_blend.stl")
    assert "master" in moai_mold.file_name("master")
    assert "pour_frame" in moai_mold.file_name("pour_frame")
    assert len(moai_mold.stl_bytes("statue")) > 1_000_000
