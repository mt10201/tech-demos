"""Rolling risk metrics built on gs_quant.timeseries (offline, no Marquee session).

All rolling metrics use gs_quant `Window(w, w)`: a trailing window of `w` observations whose first `w`
outputs (partial windows) are dropped. A value on date t uses only data up to and including t.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", module="gs_quant")

from gs_quant import timeseries as gts  # noqa: E402
from gs_quant.timeseries import Window  # noqa: E402

from .data import returns_to_index  # noqa: E402


def _win(w: int) -> Window:
    return Window(int(w), int(w))


def rolling_vol(r: pd.Series, w: int = 21, ann: int = 252) -> pd.Series:
    """Annualised trailing volatility in percent (gs_quant.volatility on a price index)."""
    return gts.volatility(returns_to_index(r), _win(w), annualization_factor=ann).rename(r.name)


def drawdown_series(r: pd.Series) -> pd.Series:
    """Running drawdown from the high-water mark (0 at peaks, negative below). Uses only past data."""
    idx = returns_to_index(r)
    return (idx / idx.cummax() - 1.0).rename(r.name)


def gs_max_drawdown(r: pd.Series) -> float:
    """Worst peak-to-trough decline (fraction, negative) from gs_quant.max_drawdown over the whole sample."""
    s = gts.max_drawdown(returns_to_index(r))
    return float(s.iloc[-1])


def rolling_zscore(r: pd.Series, w: int = 63) -> pd.Series:
    """Trailing z-score of the price index vs its own last `w` days (gs_quant.zscores)."""
    return gts.zscores(returns_to_index(r), _win(w)).rename(r.name)


def rolling_beta(r: pd.Series, bench: pd.Series, w: int = 63) -> pd.Series:
    """Trailing single-factor beta of r to bench over `w` common days (gs_quant.beta on returns)."""
    both = pd.concat([r, bench], axis=1, join="inner").dropna()
    if len(both) <= w:
        return pd.Series(dtype=float, name=r.name)
    out = gts.beta(both.iloc[:, 0], both.iloc[:, 1], _win(w), prices=False)
    return out.rename(r.name)


def rolling_corr(a: pd.Series, b: pd.Series, w: int = 63) -> pd.Series:
    """Trailing correlation of daily returns over `w` common days (gs_quant.correlation)."""
    both = pd.concat([a, b], axis=1, join="inner").dropna()
    if len(both) <= w:
        return pd.Series(dtype=float)
    return gts.correlation(both.iloc[:, 0], both.iloc[:, 1], _win(w), type_=gts.SeriesType.RETURNS)


def full_beta(r: pd.Series, bench: pd.Series) -> tuple[float, int]:
    both = pd.concat([r, bench], axis=1, join="inner").dropna()
    if len(both) < 20:
        return float("nan"), len(both)
    cov = np.cov(both.iloc[:, 0], both.iloc[:, 1], ddof=1)
    return float(cov[0, 1] / cov[1, 1]), len(both)


def beta_table(returns: pd.DataFrame, bench: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in returns.columns:
        row = {"series": c}
        for b in bench.columns:
            beta, n = full_beta(returns[c], bench[b])
            row[f"beta_{b}"] = beta
        row["common_days"] = n
        rows.append(row)
    return pd.DataFrame(rows).set_index("series")


def corr_matrix(returns: pd.DataFrame, min_periods: int = 20) -> pd.DataFrame:
    return returns.corr(min_periods=min_periods)


def stress_corr(returns: pd.DataFrame, spy: pd.Series, threshold: float = -0.02, min_periods: int = 5
                ) -> tuple[pd.DataFrame, int]:
    """Correlation computed only on days SPY's return was below `threshold` (e.g. -2%)."""
    days = spy[spy < threshold].index
    sub = returns.reindex(days)
    return sub.corr(min_periods=min_periods), len(days)
