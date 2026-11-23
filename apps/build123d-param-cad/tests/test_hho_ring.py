"""HHO vortex nozzle ring: aim maths, equal paths, watertight single body, connected gas cavity, 2 mm walls."""
import math
from pathlib import Path

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


V1_STL_SHA256 = "78b26a1682949855a0907e106790e76d11571415d4e24e7fd90ecc7a6d5e48e2"
V1_STL = Path("/workspace/exports/hho_vortex_ring/v1/hho_vortex_ring.stl")


def test_none_matches_v1_stl():
    """Selecting None must keep the v1 STL byte-identical (sharp top-inner edge)."""
    import hashlib
    from pathlib import Path
    p = H.RingParams(top_edge="none")
    data = H.stl_bytes(H.build(p)["ring"])
    assert hashlib.sha256(data).hexdigest() == V1_STL_SHA256
    # size is ignored when the edge is off
    data2 = H.stl_bytes(H.build(H.RingParams(top_edge="none", top_edge_size=2.5))["ring"])
    assert data2 == data
    if V1_STL.exists():
        assert data == V1_STL.read_bytes()


def test_top_edge_default_is_rounded():
    assert H.DEFAULT.top_edge == "rounded"
    assert H.DEFAULT.top_edge_size == pytest.approx(2.5)
    info = H.top_edge_info(H.DEFAULT)
    assert info["mode"] == "rounded" and not info["clamped"]
    assert info["size"] == pytest.approx(2.5)
    assert info["depth"] == pytest.approx(2.5 * math.sqrt(2.0))
    # default solid is not the v1 mesh
    import hashlib
    h = hashlib.sha256(H.stl_bytes(H.build(H.DEFAULT)["ring"])).hexdigest()
    assert h != V1_STL_SHA256


def test_top_edge_printable_overhang():
    """Every segment of the rounded / chamfer profile has overhang <= 45° (dr/dz <= 1)."""
    p = H.DEFAULT
    L = H.layout(p)
    for mode, size in (("rounded", 2.5), ("rounded", 4.0), ("chamfer", 2.5), ("chamfer", 4.0), ("none", 2.5)):
        pts = H.top_edge_profile(mode, size if mode != "none" else 0.0, L["r_cyl"], L["H"])
        for (r0, z0), (r1, z1) in zip(pts, pts[1:]):
            dz = z1 - z0
            if abs(dz) < 1e-12:
                assert abs(r1 - r0) < 1e-12  # no horizontal run (90° overhang)
                continue
            # walking down the profile, z decreases, r decreases (or stays)
            assert (r1 - r0) / dz <= 1.0 + 1e-6


def test_top_edge_clamped_keeps_wall(monkeypatch):
    """An oversized flare is reduced so >= 2 mm remains between the cut and the gas channels, and the UI is told."""
    # Default geometry still has ~4.8 mm clearance at 4 mm, so simulate a tighter channel.
    monkeypatch.setattr(H, "top_edge_gas_clearance", lambda p, L, size: 6.0 - 1.5 * size)
    p = H.RingParams(top_edge="rounded", top_edge_size=4.0)
    L = H.layout(p)
    assert L["top_edge_clamped"], L
    assert L["top_edge_size"] == pytest.approx(8 / 3, abs=0.01)  # 6 - 1.5*S = 2
    assert "2 mm of wall" in L["top_edge_note"]
    assert "reduced from 4" in L["top_edge_note"]
    assert (6.0 - 1.5 * L["top_edge_size"]) >= H.MIN_WALL - 1e-3


def test_top_edge_clamped_to_range():
    """A request above 4 mm is clipped to the 0–4 mm range (defaults still have wall to spare at 4 mm)."""
    p = H.RingParams(top_edge="rounded", top_edge_size=10.0)
    L = H.layout(p)
    assert L["top_edge_clamped"] and L["top_edge_size"] == pytest.approx(4.0)
    assert "0–4 mm range" in L["top_edge_note"]
    assert "2 mm of wall" not in L["top_edge_note"]
    assert H.top_edge_gas_clearance(p, L, 4.0) >= H.MIN_WALL


def test_top_edge_variants_solid():
    for kw in (dict(top_edge="chamfer", top_edge_size=2.5),
               dict(top_edge="rounded", top_edge_size=1.0),
               dict(top_edge="none", top_edge_size=0.0)):
        p = H.RingParams(**kw)
        assert H.verify(p, H.build(p))["ok"]
