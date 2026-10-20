"""Real-scan moai head mold master: closed genus-0 solid, 152.4 mm, attribution shipped."""

import io
from pathlib import Path

import numpy as np
import pytest
import trimesh

import moai_scan
from moai import fits_bed


@pytest.fixture(scope="module")
def head():
    return trimesh.load(io.BytesIO(moai_scan.stl_bytes()), file_type="stl")  # slicer-style reload


def test_watertight_single_solid_genus_zero(head):
    assert head.is_watertight and head.is_winding_consistent and head.is_volume
    assert len(head.split(only_watertight=False)) == 1
    # Euler characteristic V - E + F = 2 - 2g; 2 means genus 0: no through-holes / tunnels
    assert head.euler_number == 2


def test_size_mm_and_bed(head):
    assert head.extents[2] == pytest.approx(152.4, abs=0.01)
    assert head.bounds[0][2] == pytest.approx(0.0, abs=1e-6)
    assert 55 < head.extents[0] < 80 and 55 < head.extents[1] < 80
    assert fits_bed(head.vertices)
    assert 250_000 < len(head.faces) < 500_000


def test_flat_base(head):
    base = head.vertices[head.vertices[:, 2] < 1e-4]
    assert np.ptp(base[:, 0]) > 40 and np.ptp(base[:, 1]) > 30


def test_scales_and_names():
    v, _ = moai_scan.head_mesh(100.0)
    assert np.ptp(v[:, 2]) == pytest.approx(100.0, abs=1e-6)
    assert moai_scan.file_name(152.4) == "moai_head_scan_152mm.stl"


def test_preview_is_consistent():
    v, f = moai_scan.head_mesh(preview=True)
    assert np.ptp(v[:, 2]) == pytest.approx(152.4, abs=1e-6) and len(f) < 100_000


def test_attribution_shipped():
    text = (Path(moai_scan.__file__).parent / "assets" / "ATTRIBUTION.md").read_text()
    for s in ("Ryan Shackleton", "Quarry Moai - Rapa Nui/Easter Island", "CC BY 4.0", "Changes made",
              moai_scan.URL):
        assert s in text
    assert "Ryan Shackleton" in moai_scan.ATTRIBUTION and "Modified" in moai_scan.ATTRIBUTION
