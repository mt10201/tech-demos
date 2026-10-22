"""Forward-compat shims for build123d dev features (PR #1524 filter_by_value, PR #1525 fillet errors)."""
import os
import subprocess
import sys

import build123d as bd
import pytest

from b3d_compat import faulty_fillet_edges, fillet_or_explain, filter_by_value

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_filter_by_value_lengths_and_reverse():
    box = bd.Box(10, 20, 30)
    e = box.edges()
    assert len(filter_by_value(e, bd.Edge.length, 20.0)) == 4
    assert len(filter_by_value(e, bd.Edge.length, 20.0 + 1e-9)) == 4
    assert len(filter_by_value(e, bd.Edge.length, 20.0, reverse=True)) == 8
    assert len(filter_by_value(e, lambda s: round(s.length), 30)) == 4
    assert len(filter_by_value(e, bd.Edge.length, 20.1, tolerance=0.2)) == 4


def test_filter_by_value_none_never_matches():
    cyl = bd.Cylinder(5, 10)
    f = cyl.faces()
    flat = filter_by_value(f, bd.Face.radius, None)
    assert len(flat) == 0
    assert len(filter_by_value(f, bd.Face.radius, 5.0)) == 1


def test_faulty_fillet_edges_finds_a_working_subset():
    p = bd.Box(30, 20, 4) + bd.Pos(8, 0, 2) * bd.Box(14, 20, 1.5, align=(bd.Align.CENTER, bd.Align.CENTER,
                                                                         bd.Align.MIN))
    s = p.solids()[0]
    edges = list(s.edges().filter_by(bd.Axis.Z, reverse=True).filter_by_position(bd.Axis.Z, 1.9, 4))
    bad = faulty_fillet_edges(s, 2.5, edges)
    assert bad
    s.fillet(2.5, [e for i, e in enumerate(edges) if i not in bad])
    with pytest.raises(ValueError):
        fillet_or_explain(s, 2.5, edges)


def test_fillet_debug_script_runs():
    r = subprocess.run([sys.executable, os.path.join(HERE, "scripts", "fillet_debug.py")],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    assert "per-edge search" in r.stdout and "OK" in r.stdout
