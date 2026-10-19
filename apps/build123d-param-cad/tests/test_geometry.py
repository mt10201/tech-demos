"""Tests for the Rodin torus / golden-spiral groove math."""

import math

import numpy as np
import pytest

from geometry import (
    PHI,
    TorusParams,
    all_paths,
    azimuth_offset,
    cutter_radius,
    golden_spiral_radius,
    groove_path,
    min_strand_gap,
    path_radius,
    projected_limits,
    spiral_sweep,
    start_angles_deg,
    sweeps,
    validate,
    wrap_advance_deg,
)
from torus_mesh import grooved_torus_mesh, mesh_volume


def test_phi_constant():
    assert PHI == pytest.approx((1 + math.sqrt(5)) / 2)


def test_defaults_match_solidworks_sketch():
    p = TorusParams()
    assert p.major_radius == pytest.approx(1.39)
    assert p.tube_radius == pytest.approx(0.695)
    assert p.n_grooves == 12
    assert p.groove_depth == pytest.approx(0.1875)


def test_semicircle_profile():
    p = TorusParams(groove_depth=0.2, groove_width=0.4)
    assert cutter_radius(p) == pytest.approx(0.2)
    assert path_radius(p) == pytest.approx(p.tube_radius)  # axis on the surface


def test_wider_groove_is_shallower_arc_with_same_depth():
    p = TorusParams(groove_depth=0.125, groove_width=0.5)
    rho = cutter_radius(p)
    assert rho > 0.125
    # groove bottom sits exactly `depth` below the surface
    assert path_radius(p) - rho == pytest.approx(p.tube_radius - 0.125)
    # chord at the surface equals the requested width
    assert 2 * math.sqrt(rho**2 - (rho - 0.125) ** 2) == pytest.approx(0.5)


def test_twelve_poles_thirty_degrees():
    assert start_angles_deg(TorusParams()) == pytest.approx([30.0 * i for i in range(12)])


def test_top_half_is_golden_spiral_from_above():
    p = TorusParams()
    pts = groove_path(p, 0, 2001)
    top = pts[pts[:, 2] >= 0]
    q = np.hypot(top[:, 0], top[:, 1])
    ang = np.unwrap(np.arctan2(top[:, 1], top[:, 0]))
    _, q_max = projected_limits(p)
    expected = [golden_spiral_radius(q_max, a) for a in ang]
    assert np.allclose(q, expected, rtol=1e-9)
    # radius shrinks by exactly φ per quarter turn
    assert golden_spiral_radius(q_max, math.pi / 2) == pytest.approx(q_max / PHI)


def test_spiral_sweep_for_owner_dims():
    p = TorusParams()
    q_min, q_max = projected_limits(p)
    assert q_max / q_min == pytest.approx(3.0)  # 2.085 / 0.695
    assert math.degrees(spiral_sweep(q_min, q_max)) == pytest.approx(205.471, abs=1e-3)


def test_rodin_closure_chains_grooves():
    p = TorusParams(closure="rodin")
    assert wrap_advance_deg(p) == pytest.approx(510.0)
    paths = all_paths(p, 401)
    # end of groove i == start of groove i+5 (mod 12): one continuous winding
    for i in range(12):
        assert np.allclose(paths[i][-1], paths[(i + 5) % 12][0], atol=1e-9)


def test_mirror_closure_is_symmetric():
    p = TorusParams(closure="mirror")
    top, bottom = sweeps(p)
    assert top == pytest.approx(bottom)
    th = np.linspace(0, 2 * math.pi, 9)
    off = azimuth_offset(p, th)
    assert np.all(np.diff(off) >= -1e-12)  # monotone helical wrap


def test_paths_lie_on_axis_torus():
    p = TorusParams(groove_width=0.5)
    rp = path_radius(p)
    for pts in all_paths(p, 101):
        q = np.hypot(pts[:, 0], pts[:, 1])
        assert np.allclose(np.hypot(q - p.major_radius, pts[:, 2]), rp)


def test_handedness_mirrors_top_view():
    a = groove_path(TorusParams(handedness=1), 0)
    b = groove_path(TorusParams(handedness=-1), 0)
    assert np.allclose(a[:, 1], -b[:, 1]) and np.allclose(a[:, 0], b[:, 0])


def test_strand_gap():
    p = TorusParams()
    assert min_strand_gap(p) == pytest.approx(2 * math.pi * 0.695 / 12)


def test_mesh_closed_and_lighter_than_plain_torus():
    p = TorusParams()
    v, f = grooved_torus_mesh(p, n_theta=80, n_phi=320)
    plain = 2 * math.pi**2 * p.major_radius * p.tube_radius**2
    vol = mesh_volume(v, f)
    assert 0.4 * plain < vol < plain
    # deepest vertex is exactly `depth` below the tube surface
    q = np.hypot(v[:, 0], v[:, 1])
    lam = np.hypot(q - p.major_radius, v[:, 2])
    assert lam.min() == pytest.approx(p.tube_radius - p.groove_depth, abs=2e-3)
    assert lam.max() == pytest.approx(p.tube_radius)


def test_invalid_params():
    with pytest.raises(ValueError):
        validate(TorusParams(groove_width=0.2, groove_depth=0.1875))  # undercut
    with pytest.raises(ValueError):
        validate(TorusParams(tube_radius=2.0, major_radius=1.0))
    with pytest.raises(ValueError):
        validate(TorusParams(closure="bogus"))
