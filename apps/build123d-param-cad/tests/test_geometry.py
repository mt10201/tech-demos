"""Tests for golden-ratio / Rodin groove math."""

import math

import pytest

from geometry import (
    PHI,
    CardParams,
    groove_specs,
    normalized_spans,
    phi_powers,
)


def test_phi_constant():
    assert PHI == pytest.approx((1 + math.sqrt(5)) / 2)
    assert PHI == pytest.approx(1.6180339887, rel=1e-9)


def test_phi_powers_cycle():
    powers = phi_powers(12, cycle=4)
    assert len(powers) == 12
    assert powers[0] == pytest.approx(1.0)
    assert powers[1] == pytest.approx(PHI)
    assert powers[2] == pytest.approx(PHI**2)
    assert powers[3] == pytest.approx(PHI**3)
    assert powers[4] == pytest.approx(1.0)
    assert powers[7] == pytest.approx(PHI**3)


def test_normalized_spans_peak_is_l0():
    l0 = 31.45
    spans = normalized_spans(l0, 12)
    assert max(spans) == pytest.approx(l0)
    # Ratios within a cycle follow φ
    assert spans[1] / spans[0] == pytest.approx(PHI, rel=1e-9)
    assert spans[2] / spans[1] == pytest.approx(PHI, rel=1e-9)
    assert spans[3] / spans[2] == pytest.approx(PHI, rel=1e-9)


def test_twelve_grooves_thirty_degrees():
    specs = groove_specs(CardParams(coil_factor=0.0, rotation_deg=0.0))
    assert len(specs) == 12
    angles = [g.angle_deg for g in specs]
    assert angles[0] == pytest.approx(0.0)
    assert angles[1] == pytest.approx(30.0)
    assert angles[11] == pytest.approx(330.0)


def test_spans_stay_inside_band():
    p = CardParams(diameter=100, phi_scale=1.0, coil_factor=1.0)
    r_inner = 0.5 * p.diameter * p.inner_ratio
    r_outer = 0.5 * p.diameter * p.outer_ratio
    for g in groove_specs(p):
        assert g.r_start >= r_inner - 1e-6
        assert g.r_end <= r_outer + 1e-6
        assert g.span > 0


def test_invalid_params():
    with pytest.raises(ValueError):
        groove_specs(CardParams(inner_ratio=0.9, outer_ratio=0.2))
    with pytest.raises(ValueError):
        groove_specs(CardParams(groove_depth=10, thickness=2))
