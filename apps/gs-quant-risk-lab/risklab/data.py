"""Data loading: yfinance daily prices and sleeve-return CSVs.

Everything is converted to a wide frame of simple daily returns (index = date, columns = series).
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_TICKERS = ["SPY", "TLT", "GLD"]
SLEEVE_ETF_PRESET = ["SPYM", "SCHF", "SCHE", "SPTL", "VGIT", "SCHP", "IAU", "SIVR", "PDBC", "USO", "SLV", "GLD"]
BENCHMARKS = ["SPY", "TLT", "GLD"]
SAMPLE_SLEEVES_PATH = Path(__file__).with_name("sample_sleeves.csv")


def parse_tickers(text: str) -> list[str]:
    out: list[str] = []
    for tok in text.replace(";", ",").replace(" ", ",").split(","):
        t = tok.strip().upper()
        if t and t not in out:
            out.append(t)
    return out


def download_prices(tickers: list[str], start: str, end: str | None = None) -> pd.DataFrame:
    """Daily adjusted closes from yfinance. Columns that come back empty are dropped."""
    import yfinance as yf

    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False, threads=True)
    if raw is None or raw.empty:
        return pd.DataFrame()
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]].rename(columns={"Close": tickers[0]})
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    close = close.dropna(axis=1, how="all").sort_index()
    return close[[t for t in tickers if t in close.columns]]


def prices_to_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Simple daily returns per column, computed only over that column's own non-missing observations."""
    cols = {}
    for c in prices.columns:
        s = prices[c].dropna()
        cols[c] = s.pct_change().iloc[1:]
    return pd.DataFrame(cols).sort_index()


class SleeveCSVError(ValueError):
    pass


def parse_sleeve_csv(data: bytes | str | io.IOBase) -> pd.DataFrame:
    """Parse long-format `date,sleeve,return` (decimal returns, 0.01 = +1%) into a wide returns frame."""
    if isinstance(data, bytes):
        data = io.BytesIO(data)
    elif isinstance(data, str) and "\n" in data:
        data = io.StringIO(data)
    df = pd.read_csv(data)
    df.columns = [c.strip().lower() for c in df.columns]
    missing = {"date", "sleeve", "return"} - set(df.columns)
    if missing:
        raise SleeveCSVError(f"CSV is missing column(s): {', '.join(sorted(missing))}. Expected date,sleeve,return.")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["return"] = pd.to_numeric(df["return"], errors="coerce")
    df["sleeve"] = df["sleeve"].astype(str).str.strip()
    bad = df["date"].isna() | df["return"].isna() | (df["sleeve"] == "")
    if bad.all():
        raise SleeveCSVError("No valid rows: check date format and numeric returns.")
    df = df[~bad]
    if (df["return"] <= -1).any():
        raise SleeveCSVError("Returns must be decimals greater than -1 (0.01 = +1%).")
    if df["return"].abs().max() > 1.0:
        raise SleeveCSVError("A return above 100% in one day was found; returns must be decimals, not percent.")
    dups = df.duplicated(["date", "sleeve"])
    if dups.any():
        raise SleeveCSVError(f"{int(dups.sum())} duplicate (date, sleeve) rows.")
    wide = df.pivot(index="date", columns="sleeve", values="return").sort_index()
    wide.index = wide.index.tz_localize(None) if wide.index.tz is not None else wide.index
    wide.columns.name = None
    return wide


def load_sample_sleeves() -> pd.DataFrame:
    return parse_sleeve_csv(SAMPLE_SLEEVES_PATH.read_text())


def returns_to_index(r: pd.Series, base: float = 100.0) -> pd.Series:
    """Turn a return series into a price-like index; the base sits one day before the first return."""
    r = r.dropna()
    if r.empty:
        return r
    idx = base * (1.0 + r).cumprod()
    first = r.index[0] - pd.Timedelta(days=1)
    return pd.concat([pd.Series([base], index=[first]), idx]).rename(r.name)


def detect_annualization(r: pd.Series) -> int:
    """365 if the series trades on weekends (e.g. crypto), else 252."""
    r = r.dropna()
    if r.empty:
        return 252
    weekend_share = (r.index.day_of_week >= 5).mean()
    return 365 if weekend_share > 0.05 else 252


def make_sample_csv(path: Path = SAMPLE_SLEEVES_PATH, seed: int = 7) -> None:
    """Regenerate the bundled SYNTHETIC sample. Not real strategy results.

    Each sleeve = fixed exposures to real SPY/TLT/GLD daily returns + fat-tailed Student-t noise, so betas and
    stress correlations in the demo have something realistic to show. Needs network once (yfinance).
    """
    rng = np.random.default_rng(seed)
    bench = prices_to_returns(download_prices(BENCHMARKS, start="2023-01-01", end="2026-10-29")).dropna()
    n = len(bench)
    specs = {  # name: (daily drift, beta SPY, beta TLT, beta GLD, noise sd, t dof)
        "Momentum": (0.0002, 1.1, 0.0, 0.0, 0.006, 3),
        "Kelly": (0.0002, 0.6, 0.0, 0.3, 0.005, 3),
        "Kronos": (0.0001, 0.0, 0.0, 0.4, 0.006, 4),
        "Trend": (0.0002, 0.3, 0.3, 0.2, 0.005, 4),
        "MOVE": (0.0000, -0.2, 0.5, 0.0, 0.004, 2.5),
    }
    rows = []
    for name, (mu, bs, bt, bg, sd, dof) in specs.items():
        eps = rng.standard_t(dof, n) * sd / np.sqrt(dof / (dof - 2))
        r = mu + bs * bench["SPY"].values + bt * bench["TLT"].values + bg * bench["GLD"].values + eps
        r = np.clip(r, -0.25, 0.25)
        rows.append(pd.DataFrame({"date": bench.index.strftime("%Y-%m-%d"), "sleeve": name, "return": np.round(r, 6)}))
    pd.concat(rows).to_csv(path, index=False)


if __name__ == "__main__":
    make_sample_csv()
    print(f"wrote {SAMPLE_SLEEVES_PATH}")
