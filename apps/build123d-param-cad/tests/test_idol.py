"""Photo → 3D (Idol): offline tests (no network): splat reader, splat-centres route, Space error handling."""
import pytest

import idol_photo as ip
import scan_repair as sr


def test_bed_default_is_225x225x245():
    assert sr.BED_MM == (225.0, 225.0, 245.0)


def test_read_splat_and_master(tmp_path):
    p = tmp_path / "t.ply"
    ip.write_test_splat(str(p))
    xyz, op = ip.read_splat(str(p))
    assert xyz.shape == (25000, 3) and op.min() > 0.9
    out, rep, info, raw = ip.photo_to_master(splat=str(p), height_mm=60, voxel_mm=0.8)
    assert rep.ok() and rep.watertight and rep.euler == 2 and len(out.split(only_watertight=False)) == 1
    assert abs(rep.extents_mm[2] - 60) < 0.1 and rep.fits_bed


def test_cli_with_splat(tmp_path):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "cli", Path(__file__).resolve().parents[1] / "scripts" / "photo_to_idol_master.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    p = tmp_path / "t.ply"
    ip.write_test_splat(str(p))
    assert cli.main(["--splat", str(p), str(tmp_path / "o.stl"), "--height", "50", "--voxel", "0.8"]) == 0
    assert (tmp_path / "o.stl").stat().st_size > 1000


class _Job:
    def __init__(self, exc):
        self.exc = exc

    def result(self, timeout=None):
        raise self.exc


class _Client:
    def __init__(self, exc):
        self.exc = exc

    def submit(self, *a, **k):
        return _Job(self.exc)


@pytest.mark.parametrize("exc,word", [(TimeoutError(), "did not answer"),
                                      (RuntimeError("ZeroGPU quota exceeded"), "quota")])
def test_space_errors_are_clear(tmp_path, exc, word):
    pytest.importorskip("gradio_client")
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG\r\n")
    with pytest.raises(ip.IdolSpaceError, match=word):
        ip.run_idol(str(img), client=_Client(exc))
