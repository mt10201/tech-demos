"""Moai v2 hi-res master: closed genus-0 statue, unchanged height, tower-v3 tooling, original preserved."""
from __future__ import annotations

import hashlib
import math

import numpy as np
import pytest
import trimesh

import moai_mold
import moai_v2
from pathlib import Path

ORIG = Path(moai_v2.__file__).parent / "assets" / "moai_head_scan_152mm.stl"


def test_original_scan_untouched():
    assert hashlib.sha256(ORIG.read_bytes()).hexdigest() == "f2c214d8b9b32f2502e5f73ba2bfe0563575c28f25a9a0ee2cd065e2ecd8494a"


def test_v2_statue_closed_genus0_hires():
    m = moai_v2.statue()
    assert m.is_watertight and m.is_winding_consistent and m.is_volume
    assert m.euler_number == 2 and len(m.split(only_watertight=False)) == 1
    assert m.extents[2] == pytest.approx(152.4, abs=0.01) and m.bounds[0][2] == pytest.approx(0.0, abs=1e-6)
    assert len(m.faces) >= 600_000                      # finer than the 471k-triangle original
    assert moai_v2.STATUE_STL.stat().st_size < 40e6


def test_v2_face_is_the_same_scan():
    o = trimesh.load(ORIG, process=True)
    v = o.vertices
    face = (v[:, 1] < -1.0) & (np.abs(v[:, 0]) < 18) & (v[:, 2] > 20) & (v[:, 2] < 145)
    _, d, _ = trimesh.proximity.closest_point(moai_v2.statue(), v[face][::40])
    assert np.median(d) < 0.2 and d.max() < 0.8          # re-meshed at 0.25 mm, not re-sculpted


def test_v2_tooling_constants_and_clearances():
    d = moai_v2.dims()
    assert d.clearance_per_side == pytest.approx(0.25)
    assert d.wall == pytest.approx(3.0) and d.groove_depth == pytest.approx(1.6)
    assert d.groove_width == pytest.approx(3.5)
    assert (d.lip_d_out - d.lip_d_in) / 2 == pytest.approx(1.6)
    assert d.lip_d_in / 2 - d.frame_gr_out == pytest.approx(1.5)
    apothem = d.frame_id / 2 * math.cos(math.pi / moai_mold.SEG)
    assert apothem - d.max_r_mm >= 10.0                  # >= 10 mm silicone even at the flat faces
    assert d.top_cover_mm == pytest.approx(6.5, abs=0.05)
    assert d.plate_d < 150 and d.frame_od < 150 and d.frame_len < 200   # conservative Ender 2 envelope


def test_v2_master_and_frame_are_closed():
    parts = moai_v2.parts()
    sm = trimesh.Trimesh(*parts["master"], process=True)
    sf = trimesh.Trimesh(*parts["pour_frame"], process=True)
    assert sm.is_watertight and sm.euler_number == 2 and len(sm.split(only_watertight=False)) == 1
    assert sm.bounds[0][2] == pytest.approx(0.0, abs=1e-6) and sm.extents[2] == pytest.approx(155.9, abs=0.02)
    assert sf.is_watertight and sf.euler_number == 0      # a tube: genus 1 by design
