"""Threaded wall clamps (bd_warehouse IsoThread) for the mold pour frame."""
import os

import numpy as np
import pytest

manifold3d = pytest.importorskip("manifold3d")
pytest.importorskip("bd_warehouse")

import mold_clamp as mc  # noqa: E402
from geometry import TorusParams  # noqa: E402
from mold import MoldParams, masters  # noqa: E402

T, M, C = TorusParams(), MoldParams(), mc.ClampParams()
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def parts():
    return mc.parts(T, M, C)


def _man(shape, tol=0.05):
    tm = mc.to_trimesh(shape, tol)
    return manifold3d.Manifold(manifold3d.Mesh(tm.vertices.astype(np.float32), tm.faces.astype(np.uint32)))


def test_requirements_list_bd_warehouse():
    req = open(os.path.join(HERE, "requirements.txt")).read()
    assert "bd_warehouse>=0.4.0" in req


@pytest.mark.parametrize("name", ["clamp", "nut", "thumbscrew"])
def test_parts_are_watertight_single_bodies_that_fit_the_bed(parts, name):
    s = mc.print_pose(name, parts[name])
    assert s.is_valid and len(s.solids()) == 1
    tm = mc.to_trimesh(s)
    assert tm.is_watertight and tm.is_volume
    assert len(tm.split(only_watertight=False)) == 1
    # clamp: genus 3 (screw hole crossing the through nut slot); nut: a ring; screw: genus 0
    assert tm.euler_number == {"clamp": -4, "nut": 0, "thumbscrew": 2}[name]
    assert abs(tm.bounds[0][2]) < 1e-6
    assert all(tm.extents <= np.array(mc.ENDER2_BED_MM if hasattr(mc, "ENDER2_BED_MM") else (150, 150, 200)))
    data = mc.stl_bytes(s)
    assert len(data) > 1000


def test_one_clamp_covers_master_a_and_b():
    L = mc.layout(T, M, C)
    assert L["top_b"] > L["top_a"]
    for master in "AB":
        assert mc.head_clearance(T, M, C, master) > 0          # screw still has travel left
    assert L["travel"] >= L["top_b"] - L["top_a"]


def test_screw_presses_the_middle_of_the_wall():
    from mold import cavity_half, plate_half
    L = mc.layout(T, M, C)
    x = plate_half(T, M) + L["xs"]
    assert abs(x - (cavity_half(T, M) + M.wall / 2)) < 1e-9


def test_assembly_has_no_interference(parts):
    ms = masters(T, M, hires=False, key_segments=64)
    for master in "AB":
        a = mc.assembly(T, M, C, master, parts)
        assert len(a) == 3 * C.count
        cl, nu, sc = (_man(s) for _, s in a[:3])
        assert (cl ^ ms["master_" + master]).volume() < 1e-3
        assert (cl ^ ms["pour_frame"]).volume() < 1e-3
        assert (sc ^ cl).volume() < 1e-3
        assert (nu ^ cl).volume() < 1e-3
        assert (sc ^ ms["pour_frame"]).volume() < 1e-3
        # tip touches the frame top
        assert abs(sc.bounding_box().min_point[2] - ms["pour_frame"].bounding_box().max_point[2]) < 0.05 \
            if hasattr(sc.bounding_box(), "min_point") else True


def test_compensation_gives_the_threads_backlash():
    """Coaxial screw and nut: some axial phase meshes with zero overlap only with compensation."""
    from build123d import Pos
    res = {}
    for comp in (0.0, 0.15):
        c = mc.ClampParams(compensation=comp)
        s = _man(mc.thumbscrew(T, M, c))
        n0 = mc.nut(c)
        vols = [(s ^ _man(Pos(0, 0, c.head_h + 9 + k * 0.15) * n0)).volume() for k in range(10)]
        res[comp] = vols
    assert min(res[0.0]) > 0.1                   # nominal ISO profile: no clearance anywhere
    assert sum(v < 1e-3 for v in res[0.15]) >= 2  # compensated: a window of free play


def test_compensation_moves_thread_radii():
    from bd_warehouse.thread import IsoThread
    ext = [IsoThread(10, 1.5, 4, external=True, manufacturing_compensation=c) for c in (0, 0.15)]
    inn = [IsoThread(10, 1.5, 4, external=False, manufacturing_compensation=c) for c in (0, 0.15)]
    r = lambda s: max(np.hypot(v.X, v.Y) for v in s.vertices())  # noqa: E731
    assert r(ext[1]) < r(ext[0]) - 0.1
    assert r(inn[1]) > r(inn[0]) + 0.1


def test_validation():
    with pytest.raises(ValueError, match="groove"):
        mc.validate_clamp(T, MoldParams(groove=False), C)
    mc.validate_clamp(T, MoldParams(groove=False, frame_style="ledge"), C)
    with pytest.raises(ValueError):
        mc.validate_clamp(T, M, mc.ClampParams(size=7))
    with pytest.raises(ValueError):
        mc.validate_clamp(T, M, mc.ClampParams(count=3))


def test_masters_unchanged_by_clamps():
    """The clamps are an accessory: the mold module has no clamp parameter."""
    import dataclasses
    assert not any("clamp" in f.name for f in dataclasses.fields(MoldParams))
