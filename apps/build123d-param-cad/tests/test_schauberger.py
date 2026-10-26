"""Schauberger vortex set: funnel / horn / adapter are watertight single-body open pipes that fit and mate."""

import io
import math

import numpy as np
import pytest
import trimesh

import schauberger as S


@pytest.fixture(scope="module")
def parts():
    return S.build_all()


@pytest.mark.parametrize("name", ["Schauberger_Funnel", "Schauberger_Horn", "Schauberger_Adapter"])
def test_watertight_single_body_genus_one(parts, name):
    ck = S.check(parts[name])
    assert ck["watertight"] and ck["winding_consistent"] and ck["is_volume"]
    assert ck["bodies"] == 1
    assert ck["euler"] == 0           # open pipe: one through-hole
    assert ck["volume_cm3"] > 0
    assert ck["fits"]
    m = trimesh.load(io.BytesIO(S.stl_bytes(parts[name])), file_type="stl")   # survives STL round trip
    assert m.is_watertight and m.euler_number == 0


def test_funnel_inside_is_the_exact_hyperbola(parts):
    p = S.FunnelParams()
    inner, outer = S.funnel_profile(p)
    hyp = inner[1:-1]
    t = hyp[:, 1] - p.collar
    assert np.allclose(hyp[:, 0], 9450.0 / (90.0 + t), atol=1e-9)
    assert hyp[0, 0] * 2 == pytest.approx(210.0) and hyp[-1, 0] * 2 == pytest.approx(60.0)
    assert t[0] == 0 and t[-1] == pytest.approx(225.0)
    # outer wall is the inside offset by T along the normal: distance from each outer point to the curve = 2.8
    tt = np.linspace(0, 225, 20001)
    curve = np.stack([9450 / (90 + tt), p.collar + tt], -1)
    mid = outer[(outer[:, 1] > p.collar + 5) & (outer[:, 1] < p.collar + 220)]
    d = np.min(np.linalg.norm(mid[:, None, :] - curve[None, ::10, :], axis=2), axis=1)
    assert np.allclose(d, 2.8, atol=0.02)


def test_funnel_dimensions(parts):
    f = parts["Schauberger_Funnel"]
    assert f.extents[2] == pytest.approx(245.0)          # 15 collar + 225 hyperbola + 5 land
    assert f.extents[0] == pytest.approx(215.6, abs=0.01)
    v = f.vertices
    collar = v[v[:, 2] < 14.9]
    r = np.hypot(collar[:, 0], collar[:, 1])
    assert r.min() == pytest.approx(105.0, abs=1e-6) and r.max() == pytest.approx(107.8, abs=1e-6)
    land = v[v[:, 2] > 240.1]
    r = np.hypot(land[:, 0], land[:, 1])
    assert r.min() == pytest.approx(30.0, abs=1e-6) and r.max() == pytest.approx(32.8, abs=1e-6)


def test_egg_section_orientation_and_size():
    p = S.HornParams()
    ph = np.linspace(0, 2 * np.pi, 4096, endpoint=False)
    r = S.egg_polar(54.0, 54.0 / S.PHI, 0.2, ph)
    x, y = r * np.cos(ph), r * np.sin(ph)
    assert np.ptp(x) == pytest.approx(54.0, abs=1e-3) and np.ptp(y) == pytest.approx(54 / S.PHI, abs=1e-3)
    # blunt end at +x (outboard): the egg is fuller at x = +a/2 than at x = -a/2
    def width_at(xx):
        sel = np.abs(x - xx) < 0.3
        return np.ptp(y[sel])
    assert width_at(13.5) > width_at(-13.5) + 2.0
    # the indent dents the pointed (-x, axis-side) end inward by width * depth fraction
    sec = S.horn_section(p, np.array([0.0, np.pi]))
    assert sec[0] == pytest.approx(27.0, abs=1e-3)
    assert sec[1] == pytest.approx(27.0 - 13.5 * 0.25, abs=1e-3)


def test_horn_helix_phi_taper_and_tip():
    p = S.HornParams()
    d = S.horn_dims(p)
    assert d["R_end"] == pytest.approx(65 / S.PHI ** 3, abs=1e-6)
    assert d["tip_A"] == pytest.approx(54 / S.PHI ** 3, abs=1e-6)
    assert d["tip_A"] > 12 and d["tip_B"] > 7.5                       # open tip, not a jet
    assert d["pitch"] == pytest.approx(200 / 3)
    c, T, u, v, k = S.horn_path(p, np.array([0.0, 1 / 3, 2 / 3, 1.0]))
    assert np.allclose(k, S.PHI ** -np.arange(4.0))                    # 1/phi per turn
    assert np.allclose(np.hypot(c[:, 0], c[:, 1]), 65 * k)
    # right-handed: angle increases counter-clockwise while z rises
    c2, *_ = S.horn_path(p, np.array([0.0, 0.01]))
    assert math.atan2(c2[1, 1], c2[1, 0]) > 0 and c2[1, 2] > 0
    # u points away from the helix axis (blunt end outboard)
    assert np.all(np.einsum("ij,ij->i", u[:, :2], c[:, :2]) > 0)


def test_horn_bbox_and_no_self_intersection(parts):
    h = parts["Schauberger_Horn"]
    assert h.extents[0] <= 225 and h.extents[1] <= 225 and h.extents[2] <= 245
    assert h.bounds[0][2] == pytest.approx(0.0)
    g = S.horn_clearance()
    assert g["min_advance"] > 0.1           # neighbouring sections never cross (incl. the tip)
    assert g["min_turn_gap"] > 5.0          # turns stay apart


def test_horn_socket_is_straight_egg():
    p = S.HornParams()
    inner, _ = S.horn_rings(p)
    a, b = inner[0], inner[1]               # socket entrance and helix start
    dv = b - a
    assert np.allclose(np.linalg.norm(dv, axis=1), 12.0, atol=1e-9)   # pure translation, same egg
    assert np.allclose(dv, dv[0], atol=1e-9)


def test_adapter_fits_funnel_and_horn():
    ad = S.adapter_dims()
    assert ad["cup_id"] == pytest.approx(65.6 + 0.3)
    assert ad["cup_len"] == S.FunnelParams().land
    assert ad["spigot_egg_out_A"] == pytest.approx(54.0 - 0.3, abs=0.01)
    assert ad["spigot_egg_out_B"] == pytest.approx(54 / S.PHI - 0.3, abs=0.02)
    assert ad["spigot_len"] < S.HornParams().socket
    assert ad["length"] == pytest.approx(5 + 20 + 11)


def test_adapter_bore_converges():
    ph, ins, outs, _ = S.adapter_rings()
    loft = [r for z, r in ins[2:-1]]
    areas = [0.5 * np.sum(r ** 2) * 2 * np.pi / len(r) for r in loft]
    assert np.all(np.diff(areas) < 0)                       # strictly converging
    assert loft[0] == pytest.approx(np.full_like(ph, 30.0))  # flush with the Ø60 funnel bore
    for (z, ri), (z2, ro) in zip(ins[2:-1], outs[1:]):
        assert z == pytest.approx(z2) and np.all(ro - ri > 1.5)


def test_mated_assembly_has_no_interference():
    manifold3d = pytest.importorskip("manifold3d")

    def M(m):
        return manifold3d.Manifold(manifold3d.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                                                   tri_verts=np.asarray(m.faces, np.uint32)))

    f, a, h = S.assembly(S.FunnelParams(samples=91, segments=96), S.HornParams(rings_per_turn=40, segments=72),
                         S.AdapterParams(segments=72))
    F, A, H = M(f), M(a), M(h)
    assert (F ^ A).volume() < 1e-6 and (A ^ H).volume() < 1e-6 and (F ^ H).volume() < 1e-6


def test_funnel_step(tmp_path):
    pytest.importorskip("build123d")
    solid = S.funnel_step(tmp_path / "f.step", S.FunnelParams(samples=61))
    assert solid.is_valid
    assert (tmp_path / "f.step").stat().st_size > 1000
    assert solid.volume == pytest.approx(S.build_funnel(S.FunnelParams(samples=61, segments=720)).volume, rel=2e-3)
