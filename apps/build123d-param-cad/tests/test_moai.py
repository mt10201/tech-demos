"""Parametric moai: watertight, true height in mm, fits the Ender-2, landmarks."""

import io

import numpy as np
import pytest

from moai import (
    DEFAULT_HEIGHT_MM,
    Z_BROW,
    Z_CHIN,
    Z_NOSE_TIP,
    MoaiParams,
    build,
    fits_bed,
    moai_sdf,
    stl_bytes,
)


@pytest.fixture(scope="module")
def default_mesh():
    return build(MoaiParams())


def test_default_is_six_inches():
    assert DEFAULT_HEIGHT_MM == pytest.approx(152.4)


def test_stl_watertight_true_height_and_fits_bed(default_mesh):
    import trimesh

    v, f = default_mesh
    m = trimesh.load(io.BytesIO(stl_bytes(v, f)), file_type="stl")  # slicer-style reload
    assert m.is_watertight and m.is_winding_consistent and m.is_volume
    assert m.extents[2] == pytest.approx(152.4, abs=0.01)
    assert m.bounds[0][2] == pytest.approx(0.0, abs=1e-6)
    assert 50 < m.extents[0] < 70 and 40 < m.extents[1] < 60
    assert fits_bed(v)


def test_flat_base(default_mesh):
    v, f = default_mesh
    base = v[v[:, 2] < 1e-6]
    # the footprint at z = 0 is a broad flat area, not a point
    assert np.ptp(base[:, 0]) > 40 and np.ptp(base[:, 1]) > 25


def test_plinth_keeps_overall_height():
    import trimesh

    v, f = build(MoaiParams(plinth=True, resolution=120))
    m = trimesh.Trimesh(v, f, process=True)
    assert m.is_watertight and m.extents[2] == pytest.approx(152.4, abs=0.05)


def test_scales_to_any_height():
    v, _ = build(MoaiParams(height_mm=100.0, resolution=100))
    assert np.ptp(v[:, 2]) == pytest.approx(100.0, abs=0.01)


def _front_y(z, x=0.0):
    """Most forward (−y) solid point of the profile at height z on the plane x."""
    ys = np.linspace(-0.25, 0.15, 2001, dtype=np.float32)
    d = moai_sdf(np.full_like(ys, x), ys, np.full_like(ys, z))
    return float(ys[np.argmax(d < 0)])


def test_profile_landmarks():
    """Side profile: the nose projects furthest, the brow overhangs the eyes,
    the lips/chin project past the chest, and the head is ~45 % of the height."""
    nose = _front_y(Z_NOSE_TIP + 0.01)
    brow = _front_y(Z_BROW)
    lips = _front_y(0.615)
    chest = _front_y(0.45)
    eye_x = 0.068
    eye = _front_y(0.852, eye_x)
    assert nose < lips < chest  # −y is forward
    assert nose < brow
    assert brow < eye  # eye sockets sit back under the brow
    assert _front_y(Z_CHIN + 0.015) < chest  # chin projects over the chest
    assert 0.40 < 1.0 - Z_CHIN < 0.5
