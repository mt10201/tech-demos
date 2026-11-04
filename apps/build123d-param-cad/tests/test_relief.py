"""Photo → relief: offline tests (no network, no model download): relief math, frame, mesh checks, CLI."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest
import trimesh

import relief as R


def _analysed():
    img, mask, disp = R.synthetic_photo()
    return img, mask, disp, (0, 0, img.width, img.height)


@pytest.mark.parametrize("text,texture", [("", True), ("Dog", True), ("Rex 2012-2026", False)])
def test_relief_is_printable(text, texture):
    p = R.ReliefParams(text=text, texture=texture, res_mm=0.5)
    mesh, rep, ex = R.photo_to_relief(None, p, analysed=_analysed(), log=lambda *_: None)
    assert rep.ok() and rep.watertight and rep.is_volume and rep.euler == 2 and rep.pieces == 1
    assert rep.fits_bed
    x, y, z = rep.extents_mm
    assert 140 < x <= 150.5 and 135 < y <= 140.5
    # relief stands proud of the frame face but stays within niche floor + relief height
    assert p.thickness < z <= p.thickness - p.niche_depth + p.relief_mm + p.detail_mm + 0.5
    assert mesh.bounds[0][2] == pytest.approx(0, abs=1e-6)  # flat back on z = 0


def test_relief_survives_stl_roundtrip(tmp_path):
    mesh, rep, _ = R.photo_to_relief(None, R.ReliefParams(res_mm=0.5), analysed=_analysed(), log=lambda *_: None)
    f = tmp_path / "r.stl"
    mesh.export(f)
    m = trimesh.load(f, process=True)
    assert m.is_watertight and m.euler_number == 2 and len(m.split(only_watertight=False)) == 1


def test_bas_relief_compresses_and_is_bounded():
    img, mask, disp = R.synthetic_photo()
    lum = np.asarray(img.convert("L"), np.float32) / 255
    p = R.ReliefParams(detail_mm=0.0)
    h = R.bas_relief(disp, mask, lum, 0.25, p, 10.0)
    assert h.shape == mask.shape and h.min() >= -1e-6 and h.max() <= 11.0  # sharpen may overshoot slightly
    from scipy.ndimage import distance_transform_edt
    far = distance_transform_edt(mask == 0) * 0.25 > 4.0  # > 4 mm outside the subject
    assert h[far].max() < 0.05  # background stays on the niche floor (feather only near the edge)


def test_no_undercuts_heightfield():
    # a height field over (x, y) is single-valued in z by construction: no overhangs from the front
    z, grid, niche, poly, inside = R.frame_heightfield(R.ReliefParams(res_mm=0.5))
    assert np.isfinite(z).all() and z[inside].min() > 0


def test_auto_crop_inside_image():
    _, mask, _ = R.synthetic_photo()
    x0, y0, x1, y1 = R.auto_crop(mask, 1.2)
    assert x1 > x0 and y1 > y0 and (y1 - y0) / (x1 - x0) == pytest.approx(1.2, rel=0.05)


def test_cli_offline(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "cli", Path(__file__).resolve().parents[1] / "scripts" / "photo_to_relief.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(R, "analyse", lambda *a, **k: _analysed())
    img, _, _ = R.synthetic_photo()
    photo = tmp_path / "p.png"
    img.save(photo)
    out, prev = tmp_path / "o.stl", tmp_path / "o.png"
    assert cli.main([str(photo), str(out), "--text", "Dog", "--res", "0.5", "--preview", str(prev)]) == 0
    assert out.stat().st_size > 1e5 and prev.exists()
