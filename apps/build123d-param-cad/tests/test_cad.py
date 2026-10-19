"""build123d B-rep smoke test: 12 valid groove cutters + STEP export."""

import math

import pytest

from geometry import TorusParams, cutter_radius
from rodin_torus import build_cad_bodies, step_bytes


def test_cutters_valid_and_sized():
    p = TorusParams()
    torus, cutters, axes = build_cad_bodies(p)
    assert torus.volume == pytest.approx(2 * math.pi**2 * 1.39 * 0.695**2, rel=1e-6)
    assert len(cutters) == 12 and len(axes) == 12
    for c, a in zip(cutters, axes):
        assert c.is_valid
        assert c.volume == pytest.approx(math.pi * cutter_radius(p) ** 2 * a.length, rel=0.04)


def test_step_export():
    data = step_bytes(TorusParams(closure="mirror"))
    assert data.startswith(b"ISO-10303-21")
