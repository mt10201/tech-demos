"""build123d B-rep smoke test: 12 valid groove cutters + STEP export."""

import math

import pytest

from geometry import TorusParams, cutter_radius, path_radius
from rodin_torus import CLEARANCE, build_cad_bodies, step_bytes


def test_cutters_valid_and_sized():
    p = TorusParams()
    torus, cutters, axes = build_cad_bodies(p)
    assert torus.volume == pytest.approx(2 * math.pi**2 * 1.39 * 0.695**2, rel=1e-6)
    assert len(cutters) == 24 and len(axes) == 24  # photo lattice: 12 + 12
    for c, a in zip(cutters, axes):
        assert c.is_valid
        # U profile: half disc + walls up to CLEARANCE above the surface
        rho = cutter_radius(p)
        ext = p.tube_radius + CLEARANCE - path_radius(p)
        area = math.pi * rho**2 / 2 + 2 * rho * ext
        assert c.volume == pytest.approx(area * a.length, rel=0.04)


def test_step_export():
    data = step_bytes(TorusParams(pattern="mirror"))
    assert data.startswith(b"ISO-10303-21")
