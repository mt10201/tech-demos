"""Spiral wire jig: wire length consumed, OD hit, springback maths, watertight single bodies, clearances."""
import math

import numpy as np
import pytest

import spiral_jig as S


def _arm_len(p, sol):
    return float(np.linalg.norm(np.diff(sol.target, axis=0), axis=1).sum())


@pytest.mark.parametrize("p", [S.DEFAULT, S.SpiralParams(spacing="golden"), S.preset_params("1/4 cubit (130.9 mm)"),
                               S.SpiralParams(arms=1)])
def test_solve_uses_full_wire_and_hits_od(p):
    sol = S.solve(p)
    assert _arm_len(p, sol) == pytest.approx(S.arm_length(p), rel=2e-3)
    assert np.linalg.norm(np.diff(sol.wind, axis=0), axis=1).sum() == pytest.approx(_arm_len(p, sol), rel=1e-9)
    r = S.report(p, sol)
    assert r["predicted_relaxed_od_mm"] == pytest.approx(p.coil_od, abs=0.15)
    assert r["wound_od_on_jig_mm"] < p.coil_od < r["relaxed_od_if_uncompensated_mm"]


def test_presets_and_defaults():
    assert S.PRESETS["1/2 cubit (261.8 mm)"] == (pytest.approx(261.8), 46.0)
    assert S.PRESETS["1/4 cubit (130.9 mm)"] == (pytest.approx(130.9), 33.0)
    assert S.DK_SOFT_CU == pytest.approx(0.00208, abs=2e-5)


def test_calibrate_roundtrip():
    p = S.DEFAULT
    r = S.report(p)
    dk = S.calibrate_dk(r["relaxed_od_if_uncompensated_mm"], p.coil_od, p.wire_w)  # jig drawn at target, measured
    assert dk == pytest.approx(p.dk, rel=0.08)


def test_golden_flag():
    g = S.report(S.SpiralParams(spacing="golden", coil_od=30.0))
    assert g["center_hand_bend_needed"] == (g["innermost_gap_mm"] < S.GOLDEN_MIN_GAP)
    assert S.report(S.SpiralParams(spacing="golden", coil_od=30.0))["rounds_overlap"]
    assert not S.report(S.SpiralParams(spacing="golden"))["center_hand_bend_needed"]


@pytest.mark.parametrize("p", [S.DEFAULT, S.SpiralParams(spacing="golden"), S.preset_params("1/4 cubit (130.9 mm)")])
def test_parts_valid_and_clear(p):
    out, info = S.build(p)
    v = S.verify(p, out, info)
    assert set(out) == {"body", "winding_disc", "handle"}
    for k in out:
        c = v[k]
        assert c["watertight"] and c["bodies"] == 1 and c["volume_ml"] > 0 and c["min_z"] >= -1e-6 and c["fits_bed"], k
    c = v["clearance"]
    assert c["ok"], c
    assert c["wire_envelope_vs_walls_area_mm2"] < 1e-3 and c["min_wire_centre_to_wall_mm"] >= p.wire_w / 2
    assert out["body"].extents[0] == pytest.approx(p.coil_od + 24, abs=0.5)


def test_v1_lugs_unchanged_and_v2_teeth_valid():
    import hashlib
    v1 = S.SpiralParams(drive="lugs")
    v2 = S.DEFAULT
    assert v2.drive == "teeth"
    o1, i1 = S.build(v1)
    o2, i2 = S.build(v2)
    assert S.stl_bytes(o1["body"]) == S.stl_bytes(o2["body"])            # body reusable
    assert S.report(v1) == S.report(v2)                                  # coil numbers unchanged
    assert o2["winding_disc"].extents[2] == pytest.approx(o1["winding_disc"].extents[2])   # no height change
    c = S.verify(v2, o2, i2)
    assert c["clearance"]["ok"] and c["clearance"]["socket_to_pin_hole_min_mm"] >= 1.0
    assert all(c[k]["ok"] for k in o2)
    ds = S.drive_strength(v2)
    assert ds["teeth"]["root_area_mm2"] >= 2.5 * ds["lugs"]["root_area_mm2"]
    assert ds["teeth"]["torque_bending_worst_Nm"] > 5 * ds["lugs"]["torque_bending_worst_Nm"]
    assert o2["handle"].volume > o1["handle"].volume and o2["winding_disc"].volume < o1["winding_disc"].volume
