from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from risklab import analytics as an
from risklab import data as dm
from risklab import tails as tl


def _rets(n=800, seed=0, dof=None, scale=0.01):
    rng = np.random.default_rng(seed)
    x = rng.standard_t(dof, n) * scale if dof else rng.normal(0, scale, n)
    return pd.Series(x, index=pd.bdate_range("2020-01-01", periods=n), name=f"s{seed}")


@pytest.mark.parametrize("fn", [
    lambda r, b: an.rolling_vol(r, 21, 252),
    lambda r, b: an.rolling_zscore(r, 63),
    lambda r, b: an.rolling_beta(r, b, 63),
    lambda r, b: an.rolling_corr(r, b, 63),
    lambda r, b: an.drawdown_series(r),
])
def test_rolling_metrics_have_no_lookahead(fn):
    """Values up to date t must not change when data after t is removed."""
    r, b = _rets(seed=1), _rets(seed=2)
    full = fn(r, b).dropna()
    cut = r.index[500]
    part = fn(r.loc[:cut], b.loc[:cut]).dropna()
    common = part.index.intersection(full.index)
    assert len(common) > 300
    pd.testing.assert_series_equal(full.loc[common], part.loc[common], check_names=False, rtol=1e-10)


def test_partial_windows_are_dropped():
    r = _rets()
    v = an.rolling_vol(r, 21).dropna()
    assert v.index[0] >= r.index[20]


def test_gs_volatility_matches_numpy_and_annualization():
    r = _rets(seed=3)
    v252 = an.rolling_vol(r, 21, 252)
    v365 = an.rolling_vol(r, 21, 365)
    expected = r.iloc[-21:].std(ddof=1) * np.sqrt(252) * 100
    assert v252.iloc[-1] == pytest.approx(expected, rel=1e-6)
    assert v365.iloc[-1] / v252.iloc[-1] == pytest.approx(np.sqrt(365 / 252))


def test_beta_recovers_known_slope():
    b = _rets(2000, seed=4)
    r = (0.7 * b + _rets(2000, seed=5) * 0.3).rename("r")
    beta, n = an.full_beta(r, b)
    assert beta == pytest.approx(0.7, abs=0.03)
    assert an.rolling_beta(r, b, 252).dropna().iloc[-1] == pytest.approx(0.7, abs=0.1)


def test_gs_max_drawdown_matches_manual():
    r = pd.Series([0.1, -0.2, -0.1, 0.05, 0.4], index=pd.bdate_range("2024-01-01", periods=5))
    idx = (1 + r).cumprod()
    manual = (idx / idx.cummax() - 1).min()
    assert an.gs_max_drawdown(r) == pytest.approx(manual)
    st = tl.drawdown_stats(r)
    assert st["max_drawdown"] == pytest.approx(manual)
    assert st["longest_underwater_days"] == 3  # days 2,3,4 under water, day 5 recovers to a new high


def test_hill_estimator_on_pareto_tail():
    rng = np.random.default_rng(0)
    x = (rng.pareto(3.0, 20000) + 1) * 0.01 * rng.choice([-1, 1], 20000)
    r = pd.Series(x, index=pd.date_range("2000-01-01", periods=20000))
    alpha, _ = tl.hill_point(r, "left")
    assert alpha == pytest.approx(3.0, rel=0.15)


def test_kurtosis_and_cvar():
    g = _rets(20000, seed=6)
    t3 = _rets(20000, seed=7, dof=3)
    assert abs(tl.excess_kurtosis(g)) < 0.2
    assert tl.excess_kurtosis(t3) > 3
    # Gaussian ES at 97.5%... use 95%: phi(1.645)/0.05 * sigma = 2.063 sigma
    assert tl.hist_cvar(g, 0.95) == pytest.approx(2.063 * 0.01, rel=0.05)
    boot = tl.block_bootstrap_cvar(g, 0.95, block=10, n_boot=200)
    assert boot["p05"] < tl.hist_cvar(g, 0.95) < boot["p95"]
    assert tl.hist_cvar(g, 0.99) > tl.hist_cvar(g, 0.95)


def test_stable_fit_separates_gaussian_from_fat_tails():
    assert tl.stable_fit(_rets(5000, seed=8))["alpha"] > 1.9
    assert tl.stable_fit(_rets(5000, seed=9, dof=2))["alpha"] < 1.7


def test_stress_corr_uses_only_stress_days():
    spy = pd.Series([-0.03, 0.01, -0.025, 0.02, -0.04, -0.021, 0.0],
                    index=pd.bdate_range("2024-01-01", periods=7))
    other = pd.Series([-0.01, 0.5, -0.02, -0.5, -0.03, -0.015, 0.1], index=spy.index)
    df = pd.DataFrame({"SPY": spy, "X": other})
    c, n = an.stress_corr(df, spy, -0.02, min_periods=3)
    assert n == 4
    assert c.loc["SPY", "X"] > 0.5  # together on stress days...
    assert an.corr_matrix(df, min_periods=3).loc["SPY", "X"] < 0  # ...but negative over the full sample


def test_sleeve_csv_parse_and_validation():
    wide = dm.parse_sleeve_csv("date,sleeve,return\n2024-01-02,A,0.01\n2024-01-02,B,-0.02\n2024-01-03,A,0.0\n")
    assert list(wide.columns) == ["A", "B"] and wide.shape == (2, 2)
    with pytest.raises(dm.SleeveCSVError, match="missing"):
        dm.parse_sleeve_csv("date,name,ret\n2024-01-02,A,0.01\n")
    with pytest.raises(dm.SleeveCSVError, match="percent"):
        dm.parse_sleeve_csv("date,sleeve,return\n2024-01-02,A,5\n2024-01-03,A,1\n")
    with pytest.raises(dm.SleeveCSVError, match="duplicate"):
        dm.parse_sleeve_csv("date,sleeve,return\n2024-01-02,A,0.01\n2024-01-02,A,0.02\n")


def test_bundled_sample_loads():
    s = dm.load_sample_sleeves()
    assert {"Momentum", "Kelly", "Kronos", "Trend", "MOVE"} <= set(s.columns)
    assert len(s) > 500 and s.abs().max().max() < 0.3


def test_annualization_detection():
    assert dm.detect_annualization(_rets()) == 252
    crypto = pd.Series(0.0, index=pd.date_range("2024-01-01", periods=100))
    assert dm.detect_annualization(crypto) == 365


def test_app_smoke(monkeypatch):
    """Run the whole Streamlit script offline with synthetic prices."""
    from streamlit.testing.v1 import AppTest

    def fake_download(tickers, start, end=None):
        idx = pd.bdate_range("2018-01-01", "2024-12-31")
        rng = np.random.default_rng(1)
        return pd.DataFrame({t: 100 * np.exp(np.cumsum(rng.standard_t(4, len(idx)) * 0.01)) for t in tickers},
                            index=idx)

    monkeypatch.setattr(dm, "download_prices", fake_download)
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=120).run()
    assert not at.exception, at.exception
    assert len(at.tabs) == 4
    assert any("Stress-only" in s.value for s in at.subheader)
