"""Fetch and clean OHLCV candles into the column layout Kronos expects.

Kronos wants: timestamps, open, high, low, close, volume, amount.
`amount` (traded value) is approximated as volume * mean(OHLC) when the source has none.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

PRICE_COLS = ["open", "high", "low", "close"]
KRONOS_COLS = PRICE_COLS + ["volume", "amount"]

INTERVALS = ["5m", "15m", "1h", "1d"]
INTERVAL_DELTA = {
    "5m": pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "1d": pd.Timedelta(days=1),
}
# Longest history yfinance serves per interval.
YF_PERIOD = {"5m": "60d", "15m": "60d", "1h": "730d", "1d": "10y"}


def clean_ohlcv(raw: pd.DataFrame, tz: str | None = None) -> pd.DataFrame:
    """Normalise any OHLCV frame into `timestamps + KRONOS_COLS`.

    - Accepts a DatetimeIndex or a timestamp/date/datetime column, any column case.
    - Converts tz-aware stamps to `tz` (or keeps their own zone) and drops the zone,
      so Kronos's minute/hour/weekday features are in local market time.
    - Drops rows with missing or non-positive prices, duplicates; sorts by time.
    - Fills missing volume with 0 and derives `amount` if absent.
    """
    if raw is None or len(raw) == 0:
        raise ValueError("No candles returned for this symbol/interval.")
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):  # yfinance multi-ticker layout
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    ts_col = next((c for c in ("timestamps", "timestamp", "datetime", "date", "time") if c in df.columns), None)
    if ts_col is not None:
        ts = df[ts_col]
        if np.issubdtype(ts.dtype, np.number):
            ts = pd.to_datetime(ts, unit="ms", utc=True)
        else:
            ts = pd.to_datetime(ts)
    else:
        ts = pd.to_datetime(pd.Series(df.index, index=df.index))
    ts = pd.Series(pd.DatetimeIndex(ts), index=df.index)
    if ts.dt.tz is not None:
        if tz:
            ts = ts.dt.tz_convert(tz)
        ts = ts.dt.tz_localize(None)

    missing = [c for c in PRICE_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing price columns: {missing}")

    out = pd.DataFrame({"timestamps": ts.values})
    for c in PRICE_COLS:
        out[c] = pd.to_numeric(df[c].values, errors="coerce")
    vol = df["volume"].values if "volume" in df.columns else np.zeros(len(df))
    out["volume"] = pd.to_numeric(vol, errors="coerce")
    out["volume"] = out["volume"].fillna(0.0).clip(lower=0.0)
    if "amount" in df.columns:
        out["amount"] = pd.to_numeric(df["amount"].values, errors="coerce").fillna(0.0)
    else:
        out["amount"] = out["volume"] * out[PRICE_COLS].mean(axis=1)

    out = out.dropna(subset=["timestamps"] + PRICE_COLS)
    out = out[(out[PRICE_COLS] > 0).all(axis=1)]
    out = out.drop_duplicates(subset="timestamps", keep="last").sort_values("timestamps")
    out = out.reset_index(drop=True)
    out[KRONOS_COLS] = out[KRONOS_COLS].astype("float64")
    if len(out) == 0:
        raise ValueError("All candles were empty after cleaning.")
    return out


def future_timestamps(history: pd.Series, interval: str, n: int, session: bool) -> pd.Series:
    """Timestamps for the next `n` candles after the last one in `history`.

    session=False: continuous (crypto trades 24/7).
    session=True:  only weekday bar times that already appear in the history
                   (e.g. 09:30..15:45 for US stocks on 15m, 00:00 for daily bars).
    """
    if n <= 0:
        return pd.Series([], dtype="datetime64[ns]", name="timestamps")
    step = INTERVAL_DELTA[interval]
    hist = pd.to_datetime(pd.Series(history)).reset_index(drop=True)
    last = hist.iloc[-1]
    out = []
    if not session:
        out = [last + step * (k + 1) for k in range(n)]
    else:
        recent = hist[hist >= last - pd.Timedelta(days=30)]
        allowed = set(recent.dt.strftime("%H:%M"))
        t = last
        guard = 0
        while len(out) < n:
            t = t + step
            guard += 1
            if guard > n * 2000:
                raise RuntimeError("Could not build future timestamps for this session.")
            if t.weekday() >= 5 or t.strftime("%H:%M") not in allowed:
                continue
            out.append(t)
    return pd.Series(pd.DatetimeIndex(out), name="timestamps")


# ---------------------------------------------------------------- network fetchers

def fetch_yfinance(symbol: str, interval: str, max_bars: int = 3000) -> pd.DataFrame:
    """Stocks, ETFs, indices or yfinance crypto (e.g. BTC-USD). Needs internet."""
    import yfinance as yf

    raw = yf.download(
        symbol.strip().upper(),
        period=YF_PERIOD[interval],
        interval=interval,
        progress=False,
        auto_adjust=False,
        multi_level_index=False,
        threads=False,
    )
    tz = None
    if getattr(raw.index, "tz", None) is not None:
        tz = str(raw.index.tz)  # yfinance gives exchange-local stamps
    return clean_ohlcv(raw, tz=tz).tail(max_bars).reset_index(drop=True)


CCXT_EXCHANGES = ["kraken", "coinbase", "okx", "binance"]


def fetch_ccxt(exchange: str, pair: str, interval: str, max_bars: int = 1500) -> pd.DataFrame:
    """Public OHLCV from a crypto exchange via ccxt (no API key). Stamps in UTC."""
    import ccxt

    ex = getattr(ccxt, exchange)({"enableRateLimit": True})
    tf_ms = int(INTERVAL_DELTA[interval].total_seconds() * 1000)
    now = ex.milliseconds()
    since = now - tf_ms * (max_bars + 2)
    rows: list[list] = []
    for _ in range(40):  # pagination guard
        batch = ex.fetch_ohlcv(pair, timeframe=interval, since=since, limit=720)
        if not batch:
            break
        rows.extend(batch)
        nxt = batch[-1][0] + tf_ms
        if nxt <= since or nxt >= now:
            break
        since = nxt
        time.sleep(ex.rateLimit / 1000.0)
    if len(rows) < 10:  # some exchanges ignore `since`; take their latest window
        rows = ex.fetch_ohlcv(pair, timeframe=interval, limit=720)
    raw = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    return clean_ohlcv(raw).tail(max_bars).reset_index(drop=True)
