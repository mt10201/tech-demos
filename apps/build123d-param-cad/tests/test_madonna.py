"""Black Madonna de Sous-Terre mold master: watertight, single body, genus 0 (Euler 2), 101.6 mm (4 in), flat base."""

import io
from pathlib import Path

import numpy as np
import pytest
import trimesh

import madonna
import madonna_page


@pytest.fixture(scope="module")
def master():
    return trimesh.load(io.BytesIO(madonna.master_stl_bytes()), file_type="stl")


def test_default_is_four_inches():
    assert madonna.DEFAULT_HEIGHT_MM == pytest.approx(101.6)


def test_master_watertight_single_solid_genus_zero(master):
    assert master.is_watertight and master.is_winding_consistent and master.is_volume
    assert len(master.split(only_watertight=False)) == 1
    assert master.euler_number == 2  # genus 0: zero through-holes or silicone-trapping tunnels


def test_master_dimensions_and_bed_fit(master):
    assert master.extents[2] == pytest.approx(101.6, abs=0.05)
    assert master.bounds[0][2] == pytest.approx(0.0, abs=1e-5)
    assert 36.0 < master.extents[0] < 50.0
    assert 40.0 < master.extents[1] < 52.0
    assert madonna.fits_bed(master.vertices)
    assert 40_000 < len(master.faces) < 120_000


def test_flat_base_on_z_zero(master):
    base = master.vertices[master.vertices[:, 2] < 1e-4]
    assert np.ptp(base[:, 0]) > 30.0 and np.ptp(base[:, 1]) > 34.0
    down = (master.face_normals[:, 2] < -0.99) & (master.triangles_center[:, 2] < 0.05)
    assert master.area_faces[down].sum() > 800.0


def test_throne_and_figure_landmarks(master):
    """Verify trapezoidal 4-post throne (wider front finials at z~48 mm, narrower rear finials at z~71 mm),
    projecting knees/child/face, and solid backrest."""
    v = master.vertices
    # Front post finials around z = 47-49 mm, y < -10 mm are wider than rear post finials around z = 70-72 mm, y > 10 mm
    front_finials = v[(v[:, 2] > 46.0) & (v[:, 2] < 50.0) & (v[:, 1] < -10.0)]
    rear_finials = v[(v[:, 2] > 69.0) & (v[:, 2] < 73.0) & (v[:, 1] > 10.0)]
    assert np.ptp(front_finials[:, 0]) > np.ptp(rear_finials[:, 0]) + 4.0

    # Crown reaches top (z = 101.6 mm)
    crown = v[v[:, 2] > 95.0]
    assert len(crown) > 50 and np.ptp(crown[:, 0]) > 10.0

    # Child's head/blessing hand/orb project forward (-Y) relative to Madonna's upper chest
    child_region = v[(v[:, 2] > 50.0) & (v[:, 2] < 68.0)]
    chest_region = v[(v[:, 2] > 70.0) & (v[:, 2] < 76.0) & (np.abs(v[:, 0]) < 8.0)]
    assert child_region[:, 1].min() < chest_region[:, 1].min() - 4.0


def test_live_parametric_sdf_build_and_plinth():
    p = madonna.MadonnaParams(height_mm=101.6, resolution=110)
    v, f = madonna.build(p)
    m = trimesh.Trimesh(v, f, process=True)
    assert m.is_watertight and m.is_volume
    assert len(m.split(only_watertight=False)) == 1
    assert m.euler_number == 2
    assert m.extents[2] == pytest.approx(101.6, abs=0.05)
    assert m.bounds[0][2] == pytest.approx(0.0, abs=1e-5)

    # With extra sub-plinth enabled, total height remains 101.6 mm and genus 0
    vp, fp = madonna.build(madonna.MadonnaParams(height_mm=101.6, plinth=True, resolution=100))
    mp = trimesh.Trimesh(vp, fp, process=True)
    assert mp.is_watertight and mp.extents[2] == pytest.approx(101.6, abs=0.08)


def test_scaling_and_preview_consistency():
    v_prev, f_prev = madonna.master_mesh(127.0, preview=True)
    assert np.ptp(v_prev[:, 2]) == pytest.approx(127.0, abs=1e-5)
    assert len(f_prev) < 50_000
    assert madonna.file_name(101.6) == "black_madonna_101.6mm.stl"
    fig = madonna_page.figure(v_prev, f_prev, madonna_page.VIEWS["Front"])
    assert len(fig.data) == 1


def test_attribution_documented():
    text = (Path(madonna.__file__).parent / "assets" / "ATTRIBUTION.md").read_text()
    for token in ("black_madonna_101.6mm.stl", "Black Madonna de Sous-Terre", "Chartres", "CC0"):
        assert token in text
