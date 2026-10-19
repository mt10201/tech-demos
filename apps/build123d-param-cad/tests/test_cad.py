"""build123d B-rep smoke test: 12 valid groove cutters + STEP export."""

import math

import pytest

from geometry import TorusParams, cutter_radius, path_radius
from rodin_torus import CLEARANCE, build_cad_bodies, step_bytes


def test_cutters_valid_and_sized():
    p = TorusParams()
    torus, cutters, axes = build_cad_bodies(p)
    assert torus.volume == pytest.approx(2 * math.pi**2 * p.major_radius * p.tube_radius**2, rel=1e-6)
    assert len(cutters) == 24 and len(axes) == 24  # photo lattice: 12 + 12
    for c, a in zip(cutters, axes):
        assert c.is_valid
        # U profile: half disc + walls up to CLEARANCE above the surface
        rho = cutter_radius(p)
        ext = p.tube_radius + CLEARANCE - path_radius(p)
        area = math.pi * rho**2 / 2 + 2 * rho * ext
        assert c.volume == pytest.approx(area * a.length, rel=0.04)


def test_step_export_is_millimetres(tmp_path):
    from build123d import import_step

    data = step_bytes(TorusParams(pattern="mirror"))
    assert data.startswith(b"ISO-10303-21")
    assert b"SI_UNIT(.MILLI.,.METRE.)" in data
    path = tmp_path / "t.step"
    path.write_bytes(data)
    torus = [s for s in import_step(str(path)).solids()
             if abs(s.bounding_box().size.Z - 41.667) < 0.01]
    assert torus, "plain torus (41.67 mm tall) not found in the STEP"
    size = torus[0].bounding_box().size
    assert size.X == pytest.approx(125.0, abs=0.05) and size.Y == pytest.approx(125.0, abs=0.05)
