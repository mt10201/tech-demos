import math

import pytest

from kronos_demo.metrics import band_coverage, directional_accuracy, end_direction_hit, mae, mape, score


def test_mae_mape():
    assert mae([100, 110], [90, 110]) == pytest.approx(5.0)
    assert mape([100, 200], [110, 180]) == pytest.approx(10.0)
    assert math.isnan(mape([0, 0], [1, 1]))


def test_directional_accuracy():
    # actual: up, down, up ; forecast: up, up, up -> 2/3
    assert directional_accuracy([101, 100, 102], [101, 102, 103], last_close=100) == pytest.approx(2 / 3)
    # flat actual steps are skipped
    assert directional_accuracy([100, 101], [99, 102], last_close=100) == pytest.approx(1.0)
    assert math.isnan(directional_accuracy([100, 100], [101, 99], last_close=100))


def test_end_direction_and_coverage():
    assert end_direction_hit([95, 105], [99, 101], last_close=100)
    assert not end_direction_hit([95, 99], [99, 101], last_close=100)
    assert band_coverage([1, 5, 10], [0, 0, 0], [6, 6, 6]) == pytest.approx(2 / 3)


def test_score_keys():
    s = score([101, 102], [101, 101], [100, 100], [103, 103], last_close=100)
    assert set(s) == {"MAE (close)", "MAPE (close, %)", "Directional accuracy", "End direction hit", "Band coverage"}
    assert s["Band coverage"] == 1.0
