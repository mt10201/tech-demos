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
    GROOVE_FLOOR_MIN,
    frame_dims,
    frame_z0,
    groove_dims,
    halves_identical,
    island_half,
    key_offset,
    key_torus_gap,
    masters,
    part_sizes,
    plate_half,
    plate_thickness_a,
    plate_thickness_b,
    stl_bytes_mm,
    torus_outer_radius_mm,
    to_arrays,
    validate_mold,
)

T = TorusParams()  # royal cubit: R 41.667, r 20.833 mm
M = MoldParams()  # locating groove on (default)
M0 = MoldParams(groove=False)  # the original butt-jointed layout


@pytest.fixture(scope="module")
def parts():
    return masters(T, M, hires=True)


def test_default_sizes_fit_ender2():
    s = part_sizes(T, M0)
    assert ENDER2_BED_MM == (150.0, 150.0, 200.0)
    assert s["master_A"] == pytest.approx((139.0, 139.0, 24.833), abs=0.01)
    assert s["master_B"] == pytest.approx((139.0, 139.0, 30.833), abs=0.01)  # 10 mm plate for sockets
    assert s["pour_frame"] == pytest.approx((145.6, 145.6, 34.833), abs=0.01)
    assert all(fits_bed(v) for v in s.values())
    fo, fi, fh = frame_dims(T, M0)
    assert fi - 2 * plate_half(T, M0) == pytest.approx(2 * M0.clearance)  # snug fit
    assert fh == pytest.approx(M0.plate_thickness + 20.833 + M0.cover, abs=1e-3)


def test_groove_default_sizes_fit_ender2():
    s = part_sizes(T, M)
    assert s["master_A"] == pytest.approx((149.1, 149.1, 24.833), abs=0.01)
    assert s["master_B"] == pytest.approx((149.1, 149.1, 30.833), abs=0.01)
    # same frame footprint as before; 2 mm shorter (it stands in a 1.6 mm groove, not on the table)
    assert s["pour_frame"] == pytest.approx((145.6, 145.6, 32.433), abs=0.01)
    assert s["pour_frame"][:2] == part_sizes(T, M0)["pour_frame"][:2]
    assert all(fits_bed(v) for v in s.values())


def test_ledge_style_same_footprint():
    m = MoldParams(frame_style="ledge", groove=False)
    s = part_sizes(T, m)
    assert s["master_A"][0] == pytest.approx(145.6, abs=0.01) == s["pour_frame"][0]
    assert all(fits_bed(v) for v in s.values())


def test_big_margin_does_not_fit():
    assert not fits_bed(part_sizes(T, MoldParams(margin=15.0))["pour_frame"])
    assert not fits_bed(part_sizes(T, MoldParams(margin=8.0))["master_A"])  # groove lip needs room


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
    assert len(m.split(only_watertight=False)) == 1  # single shell
    # masters: no tunnels (genus 0); the frame is a ring (genus 1)
    assert parts[name].genus() == (1 if name == "pour_frame" else 0)


# ---- locating groove -----------------------------------------------------------

@pytest.fixture(scope="module")
def ledge_parts():
    return masters(T, MoldParams(frame_style="ledge"), hires=False, key_segments=64)


def test_groove_dimensions():
    gi, go, d = groove_dims(T, M)
    fo, fi, _ = frame_dims(T, M)
    assert d == pytest.approx(1.6) and 1.5 <= d <= 2.0
    assert 0.2 <= M.groove_clearance <= 0.3
    assert go - gi == pytest.approx(M.wall + 2 * M.groove_clearance)  # 3.5 mm channel for a 3 mm wall
    assert fi / 2 - gi == pytest.approx(M.groove_clearance)  # inner clearance
    assert go - fo / 2 == pytest.approx(M.groove_clearance)  # outer clearance
    assert plate_half(T, M) - go == pytest.approx(M.groove_lip)
    # fully outside the torus and the keys, never through the plate
    assert gi > key_offset(T, M) + M.key_radius > torus_outer_radius_mm(T)
    assert plate_thickness_a(M) - d >= GROOVE_FLOOR_MIN
    assert frame_z0(M) == pytest.approx(-d)


def test_groove_ledge_variant():
    m = MoldParams(frame_style="ledge")
    gi, go, d = groove_dims(T, m)
    assert gi == pytest.approx(island_half(T, m))  # the island step is the inner groove wall
    assert frame_dims(T, m)[1] / 2 - gi == pytest.approx(m.clearance)
    assert frame_z0(m) == pytest.approx(-(m.ledge_height + d))
    assert plate_thickness_a(m) == pytest.approx(m.ledge_height + d + GROOVE_FLOOR_MIN)  # auto-thickened
    assert all(fits_bed(v) for v in part_sizes(T, m).values())


def _solid_at(man, x, y, z, r=0.05):
    import manifold3d as mf

    probe = mf.Manifold.cube((r, r, r), True).translate((x, y, z))
    return (man ^ probe).volume() / probe.volume()


@pytest.mark.parametrize("name", ["master_A", "master_B"])
def test_groove_is_cut_in_both_bases(parts, name):
    gi, go, d = groove_dims(T, M)
    mid = (gi + go) / 2
    man = parts[name]
    for x, y in ((mid, 0.0), (0.0, -mid), (-mid, 30.0), (40.0, mid)):  # all 4 sides
        assert _solid_at(man, x, y, -d / 2) == pytest.approx(0.0, abs=1e-6)  # channel is open
        assert _solid_at(man, x, y, -d - 0.3) == pytest.approx(1.0)  # floor under it
    lip = (go + plate_half(T, M)) / 2
    assert _solid_at(man, lip, 0.0, -0.3) == pytest.approx(1.0)  # outer lip up to the pour floor
    assert _solid_at(man, gi - 0.3, 0.0, -0.3) == pytest.approx(1.0)  # pour floor inside
    assert _solid_at(man, gi + 0.1, 0.0, -d + 0.1) == pytest.approx(0.0, abs=1e-6)


def _frame_fits(p, m):
    """The frame (in master coordinates) sits in the groove without touching either base."""
    fr = p["pour_frame"]
    for k in ("master_A", "master_B"):
        assert (fr ^ p[k]).volume() < 1e-6
    bb = fr.bounding_box()
    assert bb[2] == pytest.approx(frame_z0(m), abs=1e-6)  # bottom on the groove floor
    assert bb[3] == pytest.approx(frame_dims(T, m)[0] / 2, abs=1e-6)


def test_frame_fits_groove(parts):
    _frame_fits(parts, M)


def test_frame_fits_groove_ledge(ledge_parts):
    _frame_fits(ledge_parts, MoldParams(frame_style="ledge"))
    gi, go, d = groove_dims(T, MoldParams(frame_style="ledge"))
    a = ledge_parts["master_A"]
    assert _solid_at(a, (gi + go) / 2, 0.0, -2.0 - d / 2) == pytest.approx(0.0, abs=1e-6)  # channel open


def test_frame_bottom_chamfer(parts):
    """0.4 mm 45° chamfers on both bottom edges: the footprint is wall - 2c wide."""
    fo, fi, _ = frame_dims(T, M)
    z = frame_z0(M) + 0.05
    c = M.frame_chamfer
    fr = parts["pour_frame"]
    assert _solid_at(fr, fo / 2 - c + 0.05 - 0.04, 0.0, z, r=0.02) == pytest.approx(1.0)
    assert _solid_at(fr, fo / 2 - 0.05, 0.0, z, r=0.02) == pytest.approx(0.0, abs=1e-6)
    assert _solid_at(fr, fi / 2 + 0.05, 0.0, z, r=0.02) == pytest.approx(0.0, abs=1e-6)
    assert _solid_at(fr, fo / 2 - 0.05, 0.0, z + c + 0.1, r=0.02) == pytest.approx(1.0)  # full wall above


def test_groove_validation():
    with pytest.raises(ValueError):
        validate_mold(T, MoldParams(key_edge_gap=-0.5))  # groove would cut the keys
    with pytest.raises(ValueError):
        validate_mold(T, MoldParams(groove_depth=0.0))
    with pytest.raises(ValueError):
        validate_mold(T, MoldParams(frame_chamfer=2.0))
    validate_mold(T, MoldParams(key_edge_gap=-0.5, groove=False))


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


def test_fuse_valid_returns_one_valid_solid():
    from build123d import Box, Pos

    from mold import _fuse_valid

    a = Box(10, 10, 2)
    b = Pos(0, 0, 2) * Box(4, 4, 4)
    s = _fuse_valid(a, b)
    assert s.is_valid and len(s.solids()) == 1
    assert abs(s.volume - (200 + 16 * 3)) < 1e-6
