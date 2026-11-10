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
    from scipy.spatial import cKDTree

    o = trimesh.load(ORIG, process=True)
    b = trimesh.load(BLEND, process=True)
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
    assert d.groove_width == pytest.approx(3.5)
    assert d.silicone_side_mm == pytest.approx(10.0, abs=0.05)
    assert d.statue_sink_mm == pytest.approx(0.5)
    assert d.exposed_head_mm == pytest.approx(151.9, abs=0.05)
    assert d.top_cover_mm == pytest.approx(6.5, abs=0.05)  # fill 158.4 - exposed 151.9
    assert d.fill_above_plate_mm == pytest.approx(158.4, abs=0.05)
    assert d.master_export_height_mm == pytest.approx(155.9, abs=0.05)
    assert d.frame_id == pytest.approx(2 * (d.max_r_mm + 10.0), abs=1e-6)
    assert d.silicone_ml > 500


def test_build_parts_master_and_frame_print_pose_z0():
    parts = moai_mold.build_parts()
    d = moai_mold.dims_for()
    master = trimesh.Trimesh(*parts["master"], process=True)
    frame = trimesh.Trimesh(*parts["pour_frame"], process=True)
    assert master.is_watertight and master.euler_number == 2
    assert len(master.split(only_watertight=False)) == 1
    assert master.bounds[0][2] == pytest.approx(0.0, abs=1e-3)
    assert frame.bounds[0][2] == pytest.approx(0.0, abs=1e-3)
    assert master.extents[2] == pytest.approx(d.master_export_height_mm, abs=0.05)
    assert frame.extents[2] == pytest.approx(d.frame_len, abs=0.05)
    assert abs((d.frame_gr_out - d.frame_gr_in) - (d.wall + 2 * d.clearance_per_side)) < 1e-9


def test_stl_download_names():
    assert moai_mold.file_name("statue").endswith("v1_blend.stl")
    assert "master" in moai_mold.file_name("master")
    assert "pour_frame" in moai_mold.file_name("pour_frame")
    assert len(moai_mold.stl_bytes("statue")) > 1_000_000


def test_original_sha_constant():
    assert ORIG_SHA.startswith("f2c214d8")


def test_blend_print_pose_minz_zero_and_volume_near_original():
    o = trimesh.load(ORIG, process=True)
    b = trimesh.load(BLEND, process=True)
    assert b.bounds[0][2] == pytest.approx(0.0, abs=1e-3)
    assert abs(b.volume - o.volume) / o.volume < 0.01


def test_tower_v3_source_constants_unchanged():
    assert moai_mold.FRAME_WALL == 3.0
    assert moai_mold.CLR == 0.25
    assert moai_mold.GR_DEPTH == 1.6
    assert moai_mold.PLATE_T == 4.0
    assert moai_mold.LIP_CHANNEL == 1.5
    assert moai_mold.LIP_WIDTH == 1.6
    assert moai_mold.LIP_HEIGHT == 3.0
    assert moai_mold.OVER_APEX == 6.0  # param; actual cover is 6.5
    assert moai_mold.STATUE_SINK == 0.5
    assert moai_mold.SILICONE_SIDE == 10.0


def test_actual_cover_is_over_apex_plus_sink():
    d = moai_mold.dims_for()
    assert d.top_cover_mm == pytest.approx(d.over_apex_param_mm + d.statue_sink_mm, abs=1e-6)
    assert d.top_cover_mm == pytest.approx(6.5, abs=0.05)
    assert d.statue_height_mm == pytest.approx(152.4, abs=0.05)
    assert d.exposed_head_mm == pytest.approx(151.9, abs=0.05)


def test_master_height_plate_plus_exposed():
    d = moai_mold.dims_for()
    assert d.master_export_height_mm == pytest.approx(d.plate_t + d.exposed_head_mm, abs=0.05)
    assert d.frame_len == pytest.approx(d.fill_above_plate_mm + d.groove_depth, abs=0.05)


def test_eye_region_nn_displacement_near_zero():
    """Both eye masks: indexed NN after merge must stay tiny (eyes forced w=0)."""
    from scipy.spatial import cKDTree

    o = trimesh.load(ORIG, process=True)
    b = trimesh.load(BLEND, process=True)
    vo = o.vertices
    eye_L = (vo[:, 0] > 6) & (vo[:, 0] < 22) & (vo[:, 2] > 108) & (vo[:, 2] < 122) & (vo[:, 1] > -15) & (vo[:, 1] < 5)
    eye_R = (vo[:, 0] < -6) & (vo[:, 0] > -22) & (vo[:, 2] > 108) & (vo[:, 2] < 122) & (vo[:, 1] > -15) & (vo[:, 1] < 5)
    tree = cKDTree(b.vertices)
    dL, _ = tree.query(vo[eye_L], k=1)
    dR, _ = tree.query(vo[eye_R], k=1)
    assert float(dL.max()) < 0.15
    assert float(dR.max()) < 0.15


def test_silicone_side_at_least_10mm():
    d = moai_mold.dims_for()
    assert d.silicone_side_mm >= 10.0 - 1e-6
    assert d.silicone_ml > 1000


def test_review_candidate_labels_and_original_default():
    import moai_page
    import inspect
    assert "SUPERSEDED" in moai_page.BLEND
    assert "SUPERSEDED" in moai_page.MOLD
    assert "not recommended for reprinting" in moai_page.BLEND
    assert "not recommended for reprinting" in moai_page.MOLD
    sidebar = inspect.getsource(moai_page.sidebar)
    assert "[SCAN, V2, BLEND, MOLD, PARAMETRIC]" in sidebar and "index=0" in sidebar
    assert "st.warning" in inspect.getsource(moai_page.render_scan)
    assert "st.warning" in inspect.getsource(moai_page.render_mold)
