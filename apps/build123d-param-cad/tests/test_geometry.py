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
    min_wall,
    photo_wall_analytic,
    families,
    PHOTO_SWEEP_DEG,
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
    assert p.pattern == "photo"
    assert p.groove_depth == pytest.approx(0.125)
    assert p.groove_width == pytest.approx(0.125)


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
    p = TorusParams(pattern="rodin")
    pts = groove_path(p, 0, 2001, radius=p.tube_radius)
    top = pts[pts[:, 2] >= 0]
    q = np.hypot(top[:, 0], top[:, 1])
    ang = np.unwrap(np.arctan2(top[:, 1], top[:, 0]))
    _, q_max = projected_limits(p)
    expected = [golden_spiral_radius(q_max, a) for a in ang]
    assert np.allclose(q, expected, rtol=1e-9)
    # radius shrinks by exactly φ per quarter turn
    assert golden_spiral_radius(q_max, math.pi / 2) == pytest.approx(q_max / PHI)


def test_spiral_sweep_for_owner_dims():
    p = TorusParams(pattern="rodin", groove_depth=0.1875, groove_width=0.375)
    q_min, q_max = projected_limits(p)
    assert q_max / q_min == pytest.approx(3.0)  # 2.085 / 0.695
    assert math.degrees(spiral_sweep(q_min, q_max)) == pytest.approx(205.471, abs=1e-3)


def test_rodin_closure_chains_grooves():
    p = TorusParams(pattern="rodin")
    assert wrap_advance_deg(p) == pytest.approx(510.0)
    paths = all_paths(p, 401)
    # end of groove i == start of groove i+5 (mod 12): one continuous winding
    for i in range(12):
        assert np.allclose(paths[i][-1], paths[(i + 5) % 12][0], atol=1e-9)


def test_mirror_closure_is_symmetric():
    p = TorusParams(pattern="mirror")
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
    a = groove_path(TorusParams(pattern="rodin", handedness=1), 0)
    b = groove_path(TorusParams(pattern="rodin", handedness=-1), 0)
    assert np.allclose(a[:, 1], -b[:, 1]) and np.allclose(a[:, 0], b[:, 0])




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
        validate(TorusParams(groove_width=0.0))
    with pytest.raises(ValueError):
        validate(TorusParams(groove_depth=0.8))  # deeper than the tube radius
    with pytest.raises(ValueError):
        validate(TorusParams(tube_radius=2.0, major_radius=1.0))
    with pytest.raises(ValueError):
        validate(TorusParams(pattern="bogus"))


# ---- Photo replica lattice ------------------------------------------------

def test_photo_lattice_has_12_per_direction():
    p = TorusParams()
    assert families(p) == [1, -1]
    paths = all_paths(p, 181)
    assert len(paths) == 24
    # the two families are mirror images of each other (y → −y)
    assert np.allclose(paths[0][:, 1], -paths[12][:, 1])


def test_photo_constant_pitch_sweep():
    p = TorusParams()
    pts = groove_path(p, 0, 721)
    ang = np.unwrap(np.arctan2(pts[:, 1], pts[:, 0]))
    # rim (θ=0) → hole (θ=180°) travels the measured 150°
    assert math.degrees(ang[360] - ang[0]) == pytest.approx(PHOTO_SWEEP_DEG)
    # linear in θ (constant helix pitch)
    assert np.allclose(np.diff(ang), np.diff(ang)[0])
    assert wrap_advance_deg(p) == pytest.approx(300.0)


def test_photo_grooves_chain_into_closed_loops():
    p = TorusParams()
    paths = all_paths(p, 401)
    # 300° advance = 10 poles: end of groove i is the start of groove i+10
    for i in range(12):
        assert np.allclose(paths[i][-1], paths[(i + 10) % 12][0], atol=1e-9)


def test_photo_wall_numeric_matches_closed_form():
    for w in (0.125, 0.25, 0.375):
        p = TorusParams(groove_depth=0.125, groove_width=w)
        wall, theta = min_wall(p)
        assert wall == pytest.approx(photo_wall_analytic(p), abs=2e-3)
        assert theta == pytest.approx(180.0, abs=10.0)  # thinnest at the hole
    assert min_wall(TorusParams())[0] == pytest.approx(0.155, abs=2e-3)  # 1/8" × 1/8" default
    assert min_wall(TorusParams(groove_depth=0.1875, groove_width=0.375))[0] < 0  # merges


def test_export_mesh_watertight():
    import trimesh

    from torus_mesh import EXPORT_GRID

    v, f = grooved_torus_mesh(TorusParams(), *EXPORT_GRID)
    m = trimesh.Trimesh(vertices=v, faces=f, process=False)
    assert m.is_watertight and m.is_winding_consistent
    assert len(f) == 2 * EXPORT_GRID[0] * EXPORT_GRID[1]


# ---- constant true-3D width + U profile ------------------------------------

def test_u_profile_shape():
    from geometry import profile_depth, wall_height

    p = TorusParams()  # 1/8 wide, 1/8 deep
    assert cutter_radius(p) == pytest.approx(1 / 16)
    assert wall_height(p) == pytest.approx(1 / 16)
    assert profile_depth(p, 0.0) == pytest.approx(0.125)
    # walls are vertical: just inside the edge the cut is still ≥ the wall height
    assert profile_depth(p, 0.0624) >= 1 / 16 - 1e-9
    assert profile_depth(p, 0.0626) == 0.0
    semi = TorusParams(groove_width=0.25, groove_depth=0.125)
    assert profile_depth(semi, 0.1249) == pytest.approx(0.0, abs=5e-3)


@pytest.mark.parametrize(
    "theta_deg,label",
    [(9, "outer equator"), (99, "top"), (189, "inner equator"), (279, "bottom")],
)
def test_groove_width_constant_in_3d(theta_deg, label):
    """Measure the cut width perpendicular to groove 0 (true 3D chord).

    Angles are 9° past the 18°-spaced crossings with the other family so the
    neighbouring groove doesn't widen the measurement.
    """
    from torus_mesh import GrooveField, measure_width

    p = TorusParams()
    field = GrooveField(p)
    g0 = field.paths[0]
    j = int(round(theta_deg / 360 * (len(g0) - 1)))
    w = measure_width(p, g0, j, field)
    assert w == pytest.approx(p.groove_width, rel=0.05), label


def test_width_identical_rim_vs_hole_isolated_groove():
    from torus_mesh import GrooveField, measure_width

    p = TorusParams()
    g0 = GrooveField(p).paths[0]
    single = GrooveField(p, paths=[g0])
    n = len(g0)
    widths = [measure_width(p, g0, max(1, min(n - 2, int(f * (n - 1)))), single)
              for f in (0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875)]
    assert max(widths) / min(widths) < 1.05
    assert np.allclose(widths, 0.125, rtol=0.02)


def test_mesh_depth_is_true_depth():
    from torus_mesh import grooved_torus_mesh

    v, f, dep = grooved_torus_mesh(TorusParams(), 120, 960, return_depth=True)
    assert dep.max() == pytest.approx(0.125, abs=3e-3)
    assert dep.min() == 0.0
