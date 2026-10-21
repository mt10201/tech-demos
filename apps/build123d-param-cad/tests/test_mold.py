"""Silicone mold masters: sizes, bed fit, watertight STLs, grooves, keys."""

import io
import math

import numpy as np
import pytest

from geometry import MM_PER_IN, TorusParams, all_paths
from mold import (
    ENDER2_BED_MM,
    MoldParams,
    fits_bed,
    frame_dims,
    halves_identical,
    island_half,
    key_offset,
    key_torus_gap,
    masters,
    part_sizes,
    plate_half,
    plate_thickness_b,
    stl_bytes_mm,
    to_arrays,
    validate_mold,
)

T = TorusParams()  # royal cubit: R 41.667, r 20.833 mm
M = MoldParams()


@pytest.fixture(scope="module")
def parts():
    return masters(T, M, hires=True)


def test_default_sizes_fit_ender2():
    s = part_sizes(T, M)
    assert ENDER2_BED_MM == (150.0, 150.0, 200.0)
    assert s["master_A"] == pytest.approx((139.0, 139.0, 24.833), abs=0.01)
    assert s["master_B"] == pytest.approx((139.0, 139.0, 30.833), abs=0.01)  # 10 mm plate for sockets
    assert s["pour_frame"] == pytest.approx((145.6, 145.6, 34.833), abs=0.01)
    assert all(fits_bed(v) for v in s.values())
    fo, fi, fh = frame_dims(T, M)
    assert fi - 2 * plate_half(T, M) == pytest.approx(2 * M.clearance)  # snug fit
    assert fh == pytest.approx(M.plate_thickness + 20.833 + M.cover, abs=1e-3)


def test_ledge_style_same_footprint():
    m = MoldParams(frame_style="ledge")
    s = part_sizes(T, m)
    assert s["master_A"][0] == pytest.approx(145.6, abs=0.01) == s["pour_frame"][0]
    assert all(fits_bed(v) for v in s.values())


def test_big_margin_does_not_fit():
    assert not fits_bed(part_sizes(T, MoldParams(margin=15.0))["pour_frame"])


def test_keys_clear_torus_and_cavity():
    assert key_torus_gap(T, M) == pytest.approx(12.23, abs=0.05)
    assert key_offset(T, M) + M.key_radius < island_half(T, M)
    with pytest.raises(ValueError):
        validate_mold(T, MoldParams(margin=3.0, key_radius=12.0))
    assert plate_thickness_b(M) == pytest.approx(10.0)


@pytest.mark.parametrize("name", ["master_A", "master_B", "pour_frame"])
def test_stl_watertight_after_reload(parts, name):
    import trimesh

    m = trimesh.load(io.BytesIO(stl_bytes_mm(parts[name])), file_type="stl")
    assert m.is_watertight and m.is_winding_consistent and m.is_volume
    assert m.bounds[0][2] == pytest.approx(0.0, abs=1e-6)  # print pose: on the bed
    assert m.extents == pytest.approx(part_sizes(T, M)[name], abs=0.15)


def test_flipped_bottom_half_is_identical_to_top():
    same, rel = halves_identical(T)
    assert same and rel < 1e-6


def _measure(V_mm, F, theta_deg, flip):
    from boolean_mesh import section_width

    g0 = all_paths(T, 3601, radius=T.tube_radius)[0]
    j = int(round(theta_deg / 360 * 3600))
    S, Tn = g0[j].copy(), g0[j + 1] - g0[j - 1]
    if flip:  # master B holds the bottom half rotated 180° about X
        S *= [1, -1, -1]
        Tn = Tn * [1, -1, -1]
    return section_width(T, V_mm / MM_PER_IN, F, S, Tn / np.linalg.norm(Tn))


@pytest.mark.parametrize("name,theta,flip", [
    ("master_A", 27, False), ("master_A", 99, False), ("master_A", 153, False),
    ("master_B", 207, True), ("master_B", 279, True), ("master_B", 333, True),
])
def test_grooves_still_3175(parts, name, theta, flip):
    V, F = to_arrays(parts[name])
    w, d = _measure(V, F, theta, flip)
    assert w * MM_PER_IN == pytest.approx(3.175, abs=0.03)
    assert d * MM_PER_IN == pytest.approx(3.175, abs=0.05)


def test_bumps_on_A_sockets_on_B_register(parts):
    import manifold3d as mf

    a = key_offset(T, M)
    r = M.key_radius
    for x, y in [(a, a), (-a, a), (a, -a), (-a, -a)]:
        probe = mf.Manifold.sphere(r * 0.9, 48).translate((x, y, 0.0)).trim_by_plane((0, 0, 1), 0.0)
        cap = 2 / 3 * math.pi * (0.9 * r) ** 3
        assert (parts["master_A"] ^ probe).volume() == pytest.approx(cap, rel=0.02)  # solid bump
        assert (parts["master_B"] ^ probe).volume() < 0.01 * cap  # open air above the socket
        below = mf.Manifold.sphere(r * 0.9, 48).translate((x, y, 0.0)).trim_by_plane((0, 0, -1), 0.0)
        assert (parts["master_B"] ^ below).volume() < 0.01 * cap  # socket is hollow
    # silicone A gets dimples at (x, y); silicone B, turned over (y → −y), gets bumps
    # at (x, −y): the 4-corner layout maps onto itself, so they register.
    pts = {(round(x, 6), round(y, 6)) for x in (a, -a) for y in (a, -a)}
    assert {(x, -y) for x, y in pts} == pts


def test_hole_is_sealed_by_floor(parts):
    """The floor runs under the donut hole: master A is solid at the axis."""
    import manifold3d as mf

    probe = mf.Manifold.cylinder(1.0, 1.0, 1.0, 16).translate((0.0, 0.0, -2.0))
    assert (parts["master_A"] ^ probe).volume() == pytest.approx(math.pi, rel=0.05)
