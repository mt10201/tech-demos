"""Forecast error scores used in backtest/replay mode."""
from __future__ import annotations

import numpy as np


def _arr(x) -> np.ndarray:
    return np.asarray(x, dtype="float64").ravel()


def mae(actual, pred) -> float:
    a, p = _arr(actual), _arr(pred)
    return float(np.mean(np.abs(a - p)))


def mape(actual, pred) -> float:
    """Mean absolute percentage error, in percent. Zero actuals are ignored."""
    a, p = _arr(actual), _arr(pred)
    mask = a != 0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((a[mask] - p[mask]) / a[mask])) * 100.0)


def directional_accuracy(actual, pred, last_close: float) -> float:
    """Share of steps where the forecast moved the same way as reality.

    Step k's move is close[k] - close[k-1], with close[-1] = last context close,
    measured separately along the actual path and the forecast path.
    Steps where the actual close did not move are skipped.
    """
    a = np.concatenate([[last_close], _arr(actual)])
    p = np.concatenate([[last_close], _arr(pred)])
    da, dp = np.sign(np.diff(a)), np.sign(np.diff(p))
    mask = da != 0
    if not mask.any():
        return float("nan")
    return float(np.mean(da[mask] == dp[mask]))


def end_direction_hit(actual, pred, last_close: float) -> bool:
    """Did the forecast get the sign of the whole-horizon move right?"""
    return bool(np.sign(_arr(actual)[-1] - last_close) == np.sign(_arr(pred)[-1] - last_close))


def band_coverage(actual, lo, hi) -> float:
    """Share of actual values inside [lo, hi]."""
    a, l, h = _arr(actual), _arr(lo), _arr(hi)
    return float(np.mean((a >= l) & (a <= h)))


def score(actual_close, median_close, lo, hi, last_close: float) -> dict:
    return {
        "MAE (close)": mae(actual_close, median_close),
        "MAPE (close, %)": mape(actual_close, median_close),
        "Directional accuracy": directional_accuracy(actual_close, median_close, last_close),
        "End direction hit": end_direction_hit(actual_close, median_close, last_close),
        "Band coverage": band_coverage(actual_close, lo, hi),
    }
