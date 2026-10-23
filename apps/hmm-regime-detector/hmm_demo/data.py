"""Data loading, offline fallbacks, and return/volatility feature engineering."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

HISTORY_WINDOWS: tuple[str, ...] = ("5y", "10y", "15y", "max")
_SAMPLE_CSV = Path(__file__).resolve().parent / "sample_prices.csv"

_PERIOD_DAYS: dict[str, int | None] = {
    "5y": int(365.25 * 5),
    "10y": int(365.25 * 10),
    "15y": int(365.25 * 15),
    "max": None,
}


def normalize_tickers(
    primary_ticker: str = "SPY",
    defensive_tickers: Sequence[str] = ("TLT", "GLD"),
) -> list[str]:
    """Return an ordered, deduplicated list of uppercase ticker symbols."""
    out: list[str] = []
    for raw in [primary_ticker, *defensive_tickers]:
        sym = str(raw).strip().upper()
        if sym and sym not in out:
            out.append(sym)
    if not out:
        raise ValueError("At least one valid ticker symbol is required.")
    return out


def generate_synthetic_prices(
    tickers: Sequence[str] = ("SPY", "TLT", "GLD"),
    n_days: int = 2520,
    seed: int = 42,
    end_date: str = "2026-10-22",
) -> pd.DataFrame:
    """
    Generate a deterministic, realistic 3-regime Markov-switching daily price dataset.
    Used for fast offline unit tests or when custom tickers cannot be fetched offline.

    True regimes:
      0 = Bull / Calm (low vol, positive equity drift)
      1 = Neutral / Transition (moderate vol, flat/choppy equity drift)
      2 = Bear / High-Vol (high vol, negative equity drift, positive safe-haven drift)
    """
    rng = np.random.default_rng(seed)
    symbols = [str(t).strip().upper() for t in tickers if str(t).strip()]
    if not symbols:
        symbols = ["SPY", "TLT", "GLD"]

    trans = np.array(
        [
            [0.975, 0.022, 0.003],
            [0.035, 0.940, 0.025],
            [0.010, 0.055, 0.935],
        ],
        dtype=float,
    )

    states = np.zeros(n_days, dtype=int)
    states[0] = 0
    for t in range(1, n_days):
        states[t] = rng.choice(3, p=trans[states[t - 1]])

    # Daily drift and daily vol by regime for primary equity vs defensive assets
    primary_mu = np.array([0.00085, 0.00015, -0.00220])
    primary_sd = np.array([0.0055, 0.0110, 0.0245])

    def1_mu = np.array([0.00010, 0.00025, 0.00095])
    def1_sd = np.array([0.0060, 0.0075, 0.0105])

    def2_mu = np.array([0.00025, 0.00040, 0.00080])
    def2_sd = np.array([0.0065, 0.0080, 0.0115])

    dates = pd.bdate_range(end=pd.Timestamp(end_date), periods=n_days)
    data: dict[str, np.ndarray] = {}

    for idx, sym in enumerate(symbols):
        if idx == 0:
            r = rng.normal(primary_mu[states], primary_sd[states])
            base = 200.0
        elif idx == 1:
            r = rng.normal(def1_mu[states], def1_sd[states])
            base = 100.0
        else:
            r = rng.normal(def2_mu[states], def2_sd[states]) + 0.0001 * (idx - 2)
            base = 120.0
        r[0] = 0.0
        data[sym] = base * np.exp(np.cumsum(r))

    df = pd.DataFrame(data, index=dates)
    df.index.name = "Date"
    df.attrs["true_states"] = states
    return df


def _slice_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    cal_days = _PERIOD_DAYS.get(str(period).lower())
    if cal_days is None or df.empty:
        return df.copy()
    cutoff = df.index.max() - pd.Timedelta(days=cal_days)
    sliced = df.loc[df.index >= cutoff].copy()
    return sliced if len(sliced) >= 120 else df.copy()


def load_bundled_prices(
    tickers: Sequence[str] = ("SPY", "TLT", "GLD"),
    period: str = "10y",
) -> tuple[pd.DataFrame, str]:
    """Load prices from the bundled sample_prices.csv if available, else synthetic."""
    symbols = [str(t).strip().upper() for t in tickers if str(t).strip()]
    if _SAMPLE_CSV.exists():
        raw = pd.read_csv(_SAMPLE_CSV, parse_dates=["Date"], index_col="Date").sort_index()
        if all(s in raw.columns for s in symbols):
            sub = raw[symbols].dropna(how="any")
            return _slice_period(sub, period), "bundled cache (SPY/TLT/GLD snapshot)"

    n_days_map = {"5y": 1260, "10y": 2520, "15y": 3780, "max": 3780}
    n_days = n_days_map.get(str(period).lower(), 2520)
    syn = generate_synthetic_prices(symbols, n_days=n_days)
    return syn, "synthetic Markov-switching fallback"


def fetch_prices(
    tickers: Iterable[str] = ("SPY", "TLT", "GLD"),
    period: str = "10y",
    allow_network: bool = True,
) -> tuple[pd.DataFrame, str]:
    """
    Fetch daily adjusted close prices for `tickers` over `period`.
    Falls back to the bundled CSV / synthetic dataset if `allow_network=False`
    or if `yfinance` fails.
    """
    symbols = [str(t).strip().upper() for t in tickers if str(t).strip()]
    if not symbols:
        raise ValueError("Ticker list cannot be empty.")

    period_clean = str(period).lower()
    if period_clean not in HISTORY_WINDOWS:
        period_clean = "10y"

    if allow_network:
        try:
            import yfinance as yf

            yf_period = "max" if period_clean == "max" else period_clean
            dl = yf.download(
                symbols,
                period=yf_period,
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            if not dl.empty:
                if isinstance(dl.columns, pd.MultiIndex):
                    close = dl["Close"].copy()
                elif "Close" in dl.columns and len(symbols) == 1:
                    close = dl[["Close"]].rename(columns={"Close": symbols[0]})
                else:
                    close = dl.copy()

                if isinstance(close, pd.Series):
                    close = close.to_frame(name=symbols[0])

                missing = [s for s in symbols if s not in close.columns]
                if not missing:
                    close = close[symbols].dropna(how="any").sort_index()
                    if getattr(close.index, "tz", None) is not None:
                        close.index = close.index.tz_localize(None)
                    close.index.name = "Date"
                    if len(close) >= 120:
                        return close, "yfinance (live daily adjusted close)"
        except Exception:
            pass

    return load_bundled_prices(symbols, period=period_clean)


def compute_features(
    prices: pd.DataFrame,
    primary_ticker: str = "SPY",
    vol_window: int = 20,
) -> pd.DataFrame:
    """
    Compute daily simple returns for all tickers plus HMM emission features for
    `primary_ticker`:
      - `log_return`: daily log return ln(P_t / P_{t-1})
      - `rolling_vol`: annualized rolling realized volatility std(log_return, w) * sqrt(252)

    Note: Both `log_return` at index t and `rolling_vol` at index t use only prices
    up to and including day t (no future prices).
    """
    if vol_window < 2:
        raise ValueError("vol_window must be at least 2 trading days.")
    primary = primary_ticker.strip().upper()
    if primary not in prices.columns:
        raise KeyError(f"Primary ticker '{primary}' not found in price columns {list(prices.columns)}.")

    clean_prices = prices.sort_index().dropna(how="any").copy()
    out = pd.DataFrame(index=clean_prices.index)

    for col in clean_prices.columns:
        out[f"price_{col}"] = clean_prices[col].astype(float)
        out[f"ret_{col}"] = clean_prices[col].pct_change()

    log_ret = np.log(clean_prices[primary] / clean_prices[primary].shift(1))
    rolling_vol = log_ret.rolling(window=vol_window, min_periods=vol_window).std(ddof=1) * np.sqrt(252.0)

    out["log_return"] = log_ret
    out["rolling_vol"] = rolling_vol

    out = out.dropna(subset=["log_return", "rolling_vol"]).copy()
    out.index.name = "Date"
    return out
