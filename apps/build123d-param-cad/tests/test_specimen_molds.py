"""Concrete specimen mold masters: tower-v3 seating unchanged, watertight single bodies, bed fit."""
import math

import pytest

import moai_mold as MM
import specimen_molds as S


def test_seating_constants_are_tower_v3():
    assert (S.CLR, S.GR_DEPTH, S.FRAME_WALL, S.PLATE_T, S.LIP_CHANNEL, S.LIP_WIDTH, S.LIP_HEIGHT, S.LIP_CH) == (
        0.25, 1.6, 3.0, 4.0, 1.5, 1.6, 3.0, 0.4)
    assert S.CLR == MM.CLR and S.U_GR_OUT - S.U_GR_IN == pytest.approx(3.5)


@pytest.mark.parametrize("p", [S.CUBE_DEFAULT, S.BAR_DEFAULT])
def test_parts_valid_and_fit(p):
    d = S.dims(p)
    assert d.master_fits_bed and d.frame_fits_with_5mm_brim
    assert d.gap_corner_mm > 9.9 and d.top_cover_mm >= 10 and d.count >= 3
    parts = S.build(p)
    m, f = parts["master"], parts["pour_frame"]
    cm, cf = S.check(m), S.check(f)
    assert cm["watertight"] and cm["winding_consistent"] and cm["bodies"] == 1 and cm["genus"] == 0
    assert cf["watertight"] and cf["winding_consistent"] and cf["bodies"] == 1 and cf["genus"] == 1
    assert cm["min_z"] == 0 and cf["min_z"] == 0
    assert max(cm["footprint_mm"]) <= 150 - 2 * 2.5
    assert cm["height_mm"] == pytest.approx(S.PLATE_T + positive_h(p))
    fs = f.copy(); fs.vertices = fs.vertices + [0, 0, S.PLATE_T - S.GR_DEPTH]
    assert abs((S._man(m) ^ S._man(fs)).volume()) < 1e-3  # seated frame never collides with master


def positive_h(p):
    return S.positive_size(p)[2]


def test_cube_set_is_four_50mm_and_silicone():
    d = S.dims(S.CUBE_DEFAULT)
    assert d.specimen_mm == (50, 50, 50) and d.count == 4 and d.frame_inner_mm == (130, 130)
    assert d.silicone_ml == pytest.approx(130 * 130 * 60 / 1000 - (4 - math.pi) * 100 * 60 / 1000 - 500, abs=1.0)


def test_bar_set_ratio_and_flat_standard_does_not_fit():
    d = S.dims(S.BAR_DEFAULT)
    L, w, h = d.specimen_mm
    assert L == 4 * w and w == h == 27.5 and d.count == 3
    big = S.dims(S.SpecimenParams("bar", 40.0, 160.0, 1, 1))
    assert not big.master_fits_bed
    assert (big.plate_mm[0] + big.plate_mm[1]) / math.sqrt(2) > 150  # not even diagonally
