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
    assert 1.25 <= p.turns <= 1.75 and 50 <= p.R0 <= 55 and 160 <= p.height <= 180 and 25 <= p.lead_in <= 40
    d = S.horn_dims(p)
    assert d["R_end"] == pytest.approx(52 / S.PHI ** 1.5, abs=1e-6)
    assert d["tip_A"] == pytest.approx(54 / S.PHI ** 1.5, abs=1e-6)
    assert d["pitch"] == pytest.approx(160 / 1.5)
    hp = S.horn_path(p)
    hel = hp.part == 2
    c, k = hp.c[hel], hp.k[hel]
    assert k[0] == pytest.approx(1.0) and k[-1] == pytest.approx(S.PHI ** -1.5)       # 1/phi per turn
    rel = c[:, :2] - hp.axis_xy
    assert np.allclose(np.hypot(rel[:, 0], rel[:, 1]), 52 * k, atol=1e-9)            # R tracks the egg scale
    ang = np.unwrap(np.arctan2(rel[:, 1], rel[:, 0]))
    assert ang[-1] - ang[0] == pytest.approx(2 * np.pi * 1.5)
    assert np.all(np.diff(ang) > 0) and np.all(np.diff(c[:, 2]) > 0)                 # right-handed
    assert np.all(np.diff(hp.k) <= 1e-12)                                              # continuous taper
    # u points away from the helix axis everywhere (blunt end outboard, indent on the axis side)
    radial = hp.c[:, :2] - hp.axis_xy
    assert np.all(np.einsum("ij,ij->i", hp.u[:, :2], radial) > 0)
    # mouth and tip on the vertical flow axis
    assert hp.T[0] == pytest.approx([0, 0, 1]) and d["mouth_axis_deg"] == pytest.approx(0, abs=1e-9)
    assert d["tip_axis_deg"] <= 20.0
    assert d["tip_A"] > 12 and d["tip_B"] > 7.5                                        # open tip, not a jet


def test_horn_axial_lead_in_and_socket():
    p = S.HornParams()
    hp = S.horn_path(p)
    lead = hp.s <= p.lead_in + 1e-9
    assert hp.s[lead].max() == pytest.approx(p.lead_in)                                # 30 mm axial lead-in
    assert np.allclose(hp.c[lead, :2], 0.0, atol=1e-9)                                 # on the mouth axis
    assert np.allclose(hp.T[lead], [0, 0, 1])
    inner, _ = S.horn_rings(p, hp)
    a = inner[0]
    for i in np.nonzero(lead)[0]:                                                      # straight egg socket
        dv = inner[i] - a
        assert np.allclose(dv, [0, 0, hp.s[i]], atol=1e-9)
    assert p.socket <= p.lead_in


def test_horn_path_is_tangent_continuous_and_indent_twists():
    p = S.HornParams()
    hp = S.horn_path(p)
    turn = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", hp.T[1:], hp.T[:-1]), -1, 1)))
    assert turn.max() <= 360.0 / p.rings_per_turn               # only sampling steps: no kink at any junction
    chord = np.diff(hp.c, axis=0)
    chord /= np.linalg.norm(chord, axis=1, keepdims=True)
    mid = hp.T[1:] + hp.T[:-1]
    mid /= np.linalg.norm(mid, axis=1, keepdims=True)
    assert np.einsum("ij,ij->i", chord, mid).min() > 0.9995     # positions agree with the tangents
    inner, _ = S.horn_rings(p, hp)
    j = p.segments // 2                                         # phi = pi: the indent centre (axis side)
    depth = S.horn_section(p, np.array([np.pi]))[0]
    for i in range(len(hp.c)):
        assert inner[i][j] == pytest.approx(hp.c[i] - hp.k[i] * depth * hp.u[i], abs=1e-9)


def test_horn_bbox_and_no_self_intersection(parts):
    h = parts["Schauberger_Horn"]
    assert h.extents[0] <= 220 and h.extents[1] <= 220 and h.extents[2] <= 245
    assert h.bounds[0][2] == pytest.approx(0.0)
    m = h.vertices[h.vertices[:, 2] < 1e-6]
    assert len(m) >= 2 * S.HornParams().segments                # whole egg mouth is flat on the bed
    g = S.horn_clearance()
    assert g["min_advance"] > 0.1           # neighbouring sections never cross (bends and tip)
    assert g["min_turn_gap"] > 5.0          # turns / lead-in / tip stay apart


def test_assembly_water_path_is_vertical_in_and_out():
    fp, hp, ap = S.FunnelParams(), S.HornParams(), S.AdapterParams()
    flow = S.flow_path(fp, hp, ap)
    assert np.allclose(flow[:2, :2], 0)                         # straight down the funnel axis
    path = S.horn_path(hp)
    lead = flow[2:][path.s <= hp.lead_in + 1e-9]
    assert np.allclose(lead[:, :2], 0, atol=1e-9)               # horn lead-in colinear with the funnel axis
    assert lead[0, 2] == pytest.approx(-ap.loft)                # mouth at the adapter spigot root
    tip_dir = flow[-1] - flow[-2]
    tip_dir /= np.linalg.norm(tip_dir)
    assert math.degrees(math.acos(-tip_dir[2])) <= 20           # tip points down the same axis


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

    f, a, h = S.assembly(S.FunnelParams(samples=91, segments=96), S.HornParams(rings_per_turn=48, segments=72),
                         S.AdapterParams(segments=72))
    F, A, H = M(f), M(a), M(h)
    assert (F ^ A).volume() < 1e-6 and (A ^ H).volume() < 1e-6 and (F ^ H).volume() < 1e-6


def test_funnel_step(tmp_path):
    pytest.importorskip("build123d")
    solid = S.funnel_step(tmp_path / "f.step", S.FunnelParams(samples=61))
    assert solid.is_valid
    assert (tmp_path / "f.step").stat().st_size > 1000
    assert solid.volume == pytest.approx(S.build_funnel(S.FunnelParams(samples=61, segments=720)).volume, rel=2e-3)
