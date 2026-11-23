"""HHO vortex nozzle ring: aim maths, equal paths, watertight single body, connected gas cavity, 2 mm walls."""
import math

import numpy as np
import pytest

import hho_ring as H


@pytest.fixture(scope="module")
def built():
    return H.build(H.DEFAULT)


def test_tip_axes_point_inward_down_and_swirl():
    p = H.DEFAULT
    L = H.layout(p)
    for k, (P0, d, E) in enumerate(zip(L["starts"], L["dirs"], L["mouths"])):
        assert np.linalg.norm(d) == pytest.approx(1.0)
        assert math.degrees(math.asin(-d[2])) == pytest.approx(p.tilt_deg)          # downward tilt
        radial = P0[:2] / np.linalg.norm(P0[:2]); h = d[:2] / np.linalg.norm(d[:2])
        assert math.degrees(math.acos(-(radial @ h))) == pytest.approx(p.swirl_deg)  # swirl off pure-radial
        assert np.hypot(*E[:2]) == pytest.approx(L["r_mouth"])                        # same radius
        assert E[2] == pytest.approx(p.z_mouth)                                       # same height
        assert np.cross(np.r_[radial, 0], np.r_[h, 0])[2] > 0                        # all swirl the same way
    assert L["dirs"][0][2] < 0


def test_jets_meet_below_ring():
    j = H.jets(H.DEFAULT)
    assert j["focal_z_mm"] < 0                         # below the bottom face: flame below
    assert j["vortex_core_radius_mm"] == pytest.approx(H.DEFAULT.R_plenum * math.sin(math.radians(H.DEFAULT.swirl_deg)), abs=2e-3)
    j0 = H.jets(H.RingParams(swirl_deg=0.0))
    assert j0["vortex_core_radius_mm"] == pytest.approx(0.0, abs=2e-3)
    assert H.jets(H.RingParams(tilt_deg=40))["focal_depth_below_ring_mm"] > j["focal_depth_below_ring_mm"]


def test_split_paths_equal_direct_not():
    s = H.path_lengths(H.DEFAULT)
    assert s["max_minus_min_mm"] == pytest.approx(0.0, abs=1e-6)
    d = H.path_lengths(H.RingParams(manifold="direct"))
    assert d["max_minus_min_mm"] == pytest.approx(H.DEFAULT.R_plenum * math.pi / 2, abs=1e-2)


def test_socket_bore_and_areas():
    p = H.DEFAULT
    assert H.layout(p)["bore"] == pytest.approx(p.shank_od - 2 * p.interference)
    a = H.areas(p)
    assert a["plenum_to_tips_ratio"] > 4
    assert a["plenum_mm2"] > a["feeds_total_mm2"] and a["barb_bore_mm2"] > a["tip_orifices_total_mm2"]
    with pytest.raises(ValueError):
        H.layout(H.RingParams(feed_d=1.2))
    with pytest.raises(ValueError):
        H.layout(H.RingParams(tilt_deg=50))


def test_design_walls_at_least_2mm():
    for p in (H.DEFAULT, H.RingParams(manifold="direct"), H.RingParams(tube=list(H.BARBS)[1])):
        assert min(H.design_walls(p).values()) >= H.MIN_WALL


def test_barb_printable_and_fits_tube():
    for tube, b in H.BARBS.items():
        p = H.RingParams(tube=tube)
        assert b["root"] < b["tube_id"] < b["crest"]
        pts = H.barb_profile(p, H.layout(p))
        for (r0, z0), (r1, z1) in zip(pts, pts[1:]):
            assert z1 > z0                                   # profile always climbs
            if r1 > r0:
                assert (r1 - r0) <= (z1 - z0) + 1e-9          # outward steps <= 45 deg: no overhang


def test_ring_solid(built):
    v = H.verify(H.DEFAULT, built)
    assert v["ok"], v
    assert v["watertight"] and v["mesh_bodies"] == 1 and v["brep_solids"] == 1
    assert v["gas_cavity_bodies"] == 1 and v["cavity_reaches_inlet_and_4_sockets"]
    assert max(v["size_mm"][:2]) < 70 and v["min_z"] == pytest.approx(0, abs=1e-3)
    assert v["volume_mm3"] == pytest.approx(v["brep_volume_mm3"], rel=2e-3)


@pytest.mark.parametrize("kw", [dict(manifold="direct"), dict(tube='5/16" (7.94 mm) ID'),
                                dict(tip="ks8126", shank_od=H.TIPS["ks8126"]["od"], feed_d=1.6),
                                dict(tilt_deg=20.0, swirl_deg=15.0)])
def test_variants_solid(kw):
    p = H.RingParams(**kw)
    assert H.verify(p, H.build(p))["ok"]


def test_step_export(built, tmp_path):
    stl, step = H.export(built, tmp_path)
    assert step.read_bytes()[:13] == b"ISO-10303-21;" and stl.stat().st_size > 10000
