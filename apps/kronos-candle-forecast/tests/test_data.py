import numpy as np
import pandas as pd
import pytest

from kronos_demo.data import KRONOS_COLS, clean_ohlcv, future_timestamps
from kronos_demo.forecast import summarise_paths


def _yf_like():
    idx = pd.date_range("2026-10-20 09:30", periods=5, freq="15min", tz="America/New_York")
    df = pd.DataFrame({
        "Open": [10, 11, np.nan, 12, 13], "High": [11, 12, 12, 13, 14],
        "Low": [9, 10, 10, 11, 12], "Close": [11, 11.5, 11, 12.5, 13.5],
        "Adj Close": [11, 11.5, 11, 12.5, 13.5], "Volume": [100, np.nan, 50, 70, 80],
    }, index=idx)
    df.index.name = "Datetime"
    return df


def test_clean_yfinance_layout():
    out = clean_ohlcv(_yf_like(), tz="America/New_York")
    assert list(out.columns) == ["timestamps"] + KRONOS_COLS
    assert len(out) == 4                                 # NaN-open row dropped
    assert out["timestamps"].dt.tz is None               # tz dropped, local time kept
    assert out["timestamps"].iloc[0] == pd.Timestamp("2026-10-20 09:30")
    assert out.loc[1, "volume"] == 0.0                   # missing volume -> 0
    row = out.iloc[0]
    assert row["amount"] == pytest.approx(row["volume"] * np.mean([10, 11, 9, 11]))


def test_clean_ccxt_layout_sorts_and_dedupes():
    ms = pd.Timestamp("2026-10-21 00:00", tz="UTC").value // 10**6
    h = 3_600_000
    raw = pd.DataFrame([[ms + h, 2, 3, 1, 2.5, 5], [ms, 1, 2, 0.5, 1.5, 4], [ms + h, 2, 3, 1, 2.6, 6]],
                       columns=["timestamp", "open", "high", "low", "close", "volume"])
    out = clean_ohlcv(raw)
    assert out["timestamps"].tolist() == [pd.Timestamp("2026-10-21 00:00"), pd.Timestamp("2026-10-21 01:00")]
    assert out["close"].iloc[-1] == 2.6                 # duplicate keeps the last


def test_clean_rejects_empty_and_bad_prices():
    with pytest.raises(ValueError):
        clean_ohlcv(pd.DataFrame())
    bad = pd.DataFrame({"timestamp": [1, 2], "open": [0, -1], "high": [1, 1], "low": [0, 0], "close": [1, 1]})
    with pytest.raises(ValueError):
        clean_ohlcv(bad)


def test_future_timestamps_crypto_continuous():
    hist = pd.Series(pd.date_range("2026-10-21 22:00", periods=3, freq="h"))
    fut = future_timestamps(hist, "1h", 3, session=False)
    assert fut.tolist() == list(pd.date_range("2026-10-22 01:00", periods=3, freq="h"))


def test_future_timestamps_stock_session_skips_night_and_weekend():
    # two Fri sessions of 1h bars 09:30..15:30, last bar Fri 15:30
    days = ["2026-10-15", "2026-10-16"]
    hist = pd.Series([pd.Timestamp(f"{d} {h:02d}:30") for d in days for h in range(9, 16)])
    fut = future_timestamps(hist, "1h", 3, session=True)
    assert fut.tolist() == [pd.Timestamp("2026-10-19 09:30"), pd.Timestamp("2026-10-19 10:30"),
                            pd.Timestamp("2026-10-19 11:30")]


def test_future_timestamps_daily_business_days():
    hist = pd.Series(pd.bdate_range("2026-10-12", "2026-10-16"))  # Mon..Fri
    fut = future_timestamps(hist, "1d", 2, session=True)
    assert fut.tolist() == [pd.Timestamp("2026-10-19"), pd.Timestamp("2026-10-20")]


def test_summarise_paths_quantiles_and_consistent_candles():
    rng = np.random.default_rng(0)
    k, n = 50, 6
    paths = np.zeros((k, n, 6))
    paths[:, :, 3] = 100 + rng.normal(0, 1, (k, n))      # close
    paths[:, :, 0] = 100                                  # open
    paths[:, :, 1] = 99.0                                 # deliberately bad high
    paths[:, :, 2] = 101.0                                # deliberately bad low
    ts = pd.Series(pd.date_range("2026-10-22", periods=n, freq="h"))
    fc = summarise_paths(paths, ts)
    assert fc.median.shape == (n, 7)
    assert (fc.q[10] <= fc.q[25]).all() and (fc.q[25] <= fc.q[75]).all() and (fc.q[75] <= fc.q[90]).all()
    m = fc.median
    assert (m["high"] >= m[["open", "close"]].max(axis=1)).all()
    assert (m["low"] <= m[["open", "close"]].min(axis=1)).all()
