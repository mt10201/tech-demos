"""Tetrix brazing jig: counts, cut length, watertight single bodies on z=0, joint clearance, lift-out, bed fit."""
import math

import pytest

import tetrix_jig as T


def test_default_counts_and_cut_list():
    d = T.dims(T.DEFAULT)
    assert d.edge == pytest.approx(523.6 / 4) and d.small_edge == pytest.approx(65.45)
    assert (d.rod_count, d.joint_count) == (24, 10)
    assert d.rod_cut_length == pytest.approx(64.45)
    assert d.total_wire_mm_incl_3pct == pytest.approx(2 * 24 * 64.45 * 1.03, abs=0.1)
    alt = d.alt_continuous_outer_edges
    assert (alt["rods"], alt["long"], alt["short"]) == (18, 6, 12) and alt["long_len"] == pytest.approx(129.9)
    assert T.dims(T.TetrixParams(level=2)).rod_count == 96


def test_edges_are_cubit_harmonics():
    assert T.cubit_edges()[:3] == pytest.approx([261.8, 130.9, 65.45])


def test_default_parts_valid():
    out, info = T.build(T.DEFAULT)
    v = T.verify(T.DEFAULT, out, info)
    assert set(out) == {"rod_length_gauge", "single_tetra_jig", "assembly_plate_130.9mm", "rods_reference"}
    for k, c in v.items():
        assert c["watertight"] and c["winding_consistent"] and c["bodies"] == 1 and c["min_z"] == 0, k
        assert c["fits_bed"], k
        if k != "rods_reference":
            assert c["ok"], k
    for k in ("single_tetra_jig", "assembly_plate_130.9mm"):
        assert v[k]["min_jig_to_joint_mm"] >= T.MIN_JOINT_CLEAR
        assert v[k]["rod_interference_mm3"] == 0 and v[k]["lifts_out_vertically"]
    assert v["assembly_plate_130.9mm"]["base_cradles"] == 9 and v["assembly_plate_130.9mm"]["top_posts"] == 3


def test_gauge_lengths():
    g, gi = T.gauge(T.DEFAULT)
    assert gi["short_cut"] == pytest.approx(64.45) and gi["long_cut"] == pytest.approx(129.9)
    assert g.extents[0] == pytest.approx(gi["stop"] + 129.9, abs=1e-3)  # long cut face = stop + long length


def test_oversize_flagged():
    p = T.TetrixParams(edge=261.8, level=1)
    out, info = T.build(p)
    assert T.verify(p, out, info)["assembly_plate_261.8mm"]["ok"] is False


def test_snap_defaults_and_profile():
    p = T.DEFAULT
    assert (p.rod_d, p.clearance, p.snap_mouth, p.snap_lip) == (1.88, 0.10, 1.75, True)
    d = T.dims(p)
    assert d.seat_d == pytest.approx(1.98) and d.interference_per_side == pytest.approx(0.065)
    assert d.rod_cut_length == pytest.approx(64.45) and d.alt_continuous_outer_edges["long_len"] == pytest.approx(129.9)
    S = T.snap_profile(p, d.seat_d / 2 + T.CRADLE_TOP)
    assert S["lip"] and S["seat_wrap_deg"] > 180 and S["rm"] * 2 < p.rod_d < S["rs"] * 2


def test_snap_seats_hold_and_release():
    out, info = T.build(T.DEFAULT)
    v = T.verify(T.DEFAULT, out, info)
    for k in ("single_tetra_jig", "assembly_plate_130.9mm"):
        c = v[k]
        assert c["seat_interference_mm3"] == 0 and c["lifts_out_through_mouth"] and c["snap_holds_rod"], k
        assert c["interference_per_side_mm"] == pytest.approx(0.065)
    tj, rods, _ = T.tetra_jig(T.DEFAULT)
    for a, b in rods:                                   # every cradle (flat and sloped) has a lip
        assert not T.liftout_clear(tj, [(a, b)], 1.88) and T.liftout_clear(tj, [(a, b)], 1.73)


def test_lip_off_is_open_channel():
    p = T.TetrixParams(snap_lip=False)
    out, info = T.build(p)
    v = T.verify(p, out, info)
    assert v["single_tetra_jig"]["full_rod_lifts_without_lip_contact"] and not v["single_tetra_jig"]["snap_holds_rod"]
    assert info["rod_length_gauge"]["lip"] is False
