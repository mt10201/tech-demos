"""Kronos candle forecast demo (Streamlit, CPU-only).

Run:  streamlit run app.py
Research / visualization only. Not financial advice. Places no trades.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import streamlit as st

from kronos_demo import data as kd
from kronos_demo.charts import forecast_figure
from kronos_demo.forecast import DEFAULT_MODEL, MODELS, load_predictor, sample_paths
from kronos_demo.metrics import score

st.set_page_config(page_title="Kronos candle forecast", page_icon="🕯️", layout="wide")

DISCLAIMER = (
    "**Research / visualization only.** Kronos forecasts are probabilistic samples from a "
    "pre-trained model, not predictions you can rely on. This is not financial advice, and "
    "this app connects to no broker and places no trades."
)

# --- optional URL presets, e.g. ?market=crypto&symbol=BTC/USD&interval=1h&mode=backtest
qp = st.query_params
MARKETS = ["Stock / ETF (yfinance)", "Crypto (exchange via ccxt)", "Crypto (yfinance)"]
_market_key = {"stock": 0, "crypto": 1, "crypto-yf": 2}


def fmt(x: float) -> str:
    """Readable price: 84,461 / 344.12 / 0.004213."""
    ax = abs(x)
    if ax >= 1000:
        return f"{x:,.0f}"
    if ax >= 1:
        return f"{x:,.2f}"
    return f"{x:.4g}"


def _qp(name, default):
    return qp.get(name, default)


@st.cache_resource(show_spinner="Loading Kronos from Hugging Face (first run downloads the weights)...")
def get_predictor(name: str):
    return load_predictor(name, device="cpu")


@st.cache_data(ttl=300, show_spinner="Fetching candles...")
def get_candles(market: str, symbol: str, interval: str, exchange: str) -> pd.DataFrame:
    if market.startswith("Crypto (exchange"):
        return kd.fetch_ccxt(exchange, symbol, interval, max_bars=1500)
    return kd.fetch_yfinance(symbol, interval, max_bars=3000)


@st.cache_data(show_spinner=False, max_entries=32)
def run_forecast(model_name, context, future_ts, n_paths, T, top_p, seed):
    pred = get_predictor(model_name)
    return sample_paths(pred, context, future_ts, n_paths=n_paths, T=T, top_p=top_p, seed=seed)


# ------------------------------------------------------------------ sidebar
st.sidebar.header("Market")
market = st.sidebar.radio("Source", MARKETS, index=_market_key.get(_qp("market", "stock"), 0))
is_ccxt = market.startswith("Crypto (exchange")
if is_ccxt:
    exchange = st.sidebar.selectbox("Exchange (public data, no key)", kd.CCXT_EXCHANGES,
                                    index=kd.CCXT_EXCHANGES.index(_qp("exchange", "coinbase")))
    symbol = st.sidebar.text_input("Pair", _qp("symbol", "BTC/USD"))
    st.sidebar.caption("Binance blocks US IPs; use Coinbase/Kraken/OKX there.")
elif market == "Crypto (yfinance)":
    exchange = ""
    symbol = st.sidebar.text_input("yfinance crypto symbol", _qp("symbol", "BTC-USD"))
else:
    exchange = ""
    symbol = st.sidebar.text_input("Ticker", _qp("symbol", "AAPL"))
session = market.startswith("Stock")

interval = st.sidebar.selectbox("Interval", kd.INTERVALS, index=kd.INTERVALS.index(_qp("interval", "15m")))

st.sidebar.header("Model")
model_name = st.sidebar.selectbox("Model size", list(MODELS), index=list(MODELS).index(_qp("model", DEFAULT_MODEL)),
                                  format_func=lambda n: f"{n} ({MODELS[n][3]} params)")
max_ctx = MODELS[model_name][2]
lookback = st.sidebar.slider("Lookback (context candles)", 64, min(max_ctx, 1024),
                             min(int(_qp("lookback", 400)), min(max_ctx, 1024)), step=16)
horizon = st.sidebar.slider("Forecast horizon N (candles)", 4, 96, int(_qp("horizon", 24)), step=4)
n_paths = st.sidebar.slider("Sampled paths", 1, 50, int(_qp("paths", 16)))
with st.sidebar.expander("Sampling"):
    T = st.slider("Temperature T", 0.1, 2.0, 1.0, 0.1)
    top_p = st.slider("top_p", 0.5, 1.0, 0.9, 0.05)
    seed = st.number_input("Seed", 0, 10_000, 42)
    show_paths = st.slider("Draw individual paths", 0, 50, 0)

st.sidebar.header("Mode")
mode = st.sidebar.radio("Mode", ["Forecast (next N candles)", "Backtest / replay"],
                        index=1 if _qp("mode", "forecast") == "backtest" else 0)

# ------------------------------------------------------------------ main
st.title("🕯️ Kronos candle forecast")
st.caption(
    "Kronos ([shiyu-coder/Kronos](https://github.com/shiyu-coder/Kronos), MIT, AAAI 2026) is an "
    "open-source foundation model for OHLCV candlesticks. It samples possible future candles; "
    "the orange band shows the spread of those samples."
)
st.warning(DISCLAIMER, icon="⚠️")

try:
    df = get_candles(market, symbol, interval, exchange)
except Exception as e:  # network/symbol errors are user-facing
    st.error(f"Could not load candles for **{symbol}** ({interval}): {e}")
    st.stop()

if len(df) < 64 + horizon:
    st.error(f"Only {len(df)} candles available; need at least {64 + horizon}. Try a longer interval.")
    st.stop()

backtest = mode.startswith("Backtest")
actual = None
if backtest:
    max_back = len(df) - 64
    default_back = min(int(_qp("back", horizon)), max_back)
    back = st.slider("Cutoff: how many candles before the latest one", horizon, max_back,
                     max(horizon, default_back),
                     help="Kronos only sees candles up to the cutoff; the next N real candles are overlaid.")
    cut = len(df) - back
    actual = df.iloc[cut: cut + horizon].reset_index(drop=True)
    future_ts = actual["timestamps"]
    st.caption(f"Cutoff at **{df['timestamps'].iloc[cut - 1]}**; scoring the next {len(actual)} real candles.")
else:
    cut = len(df)
    future_ts = kd.future_timestamps(df["timestamps"], interval, horizon, session=session)

context = df.iloc[max(0, cut - lookback): cut].reset_index(drop=True)
lookback_used = len(context)

t0 = time.time()
with st.spinner(f"Sampling {n_paths} paths x {len(future_ts)} candles with {model_name} on CPU..."):
    try:
        fc = run_forecast(model_name, context, future_ts, n_paths, T, top_p, int(seed))
    except Exception as e:
        st.error(f"Kronos failed: {e}")
        st.stop()
elapsed = time.time() - t0

shown = context.tail(min(lookback_used, max(120, 4 * horizon)))
tz_note = "exchange local time" if session else "UTC"
title = f"{symbol} · {interval} · {model_name} · {n_paths} paths · times in {tz_note}"
fig = forecast_figure(shown, fc, actual=actual, title=title, session=session,
                      interval=interval, show_paths=show_paths)
st.plotly_chart(fig, width="stretch")

last_close = float(context["close"].iloc[-1])
med_close = fc.median["close"].to_numpy()
cols = st.columns(4)
cols[0].metric("Last close", fmt(last_close))
cols[1].metric(f"Median close in {len(med_close)} candles", fmt(med_close[-1]),
               f"{(med_close[-1] / last_close - 1) * 100:+.2f}%")
cols[2].metric("10-90% range at horizon", f"{fmt(fc.q[10][-1])} – {fmt(fc.q[90][-1])}")
cols[3].metric("Share of paths ending higher", f"{np.mean(fc.paths[:, -1, 3] > last_close) * 100:.0f}%")

if backtest and actual is not None and len(actual):
    s = score(actual["close"], med_close[: len(actual)], fc.q[10][: len(actual)], fc.q[90][: len(actual)], last_close)
    st.subheader("Backtest scores (median forecast vs actual)")
    c = st.columns(5)
    c[0].metric("MAE (close)", fmt(s['MAE (close)']))
    c[1].metric("MAPE (close)", f"{s['MAPE (close, %)']:.2f}%")
    c[2].metric("Directional accuracy", f"{s['Directional accuracy'] * 100:.0f}%",
                help="Share of steps where forecast and actual moved the same way (flat steps skipped).")
    c[3].metric("End direction", "✅ right" if s["End direction hit"] else "❌ wrong",
                help="Sign of the whole-horizon move vs the last context close.")
    c[4].metric("Band coverage", f"{s['Band coverage'] * 100:.0f}%",
                help="Share of actual closes inside the 10-90% band (ideal ≈ 80%).")
    naive = float(np.mean(np.abs(actual["close"].to_numpy() - last_close)))
    st.caption(f"Baseline: a flat 'no change' forecast has MAE {fmt(naive)}. "
               "One cutoff is one sample; move the cutoff to see how much scores vary.")

with st.expander("Forecast table (median candle per step + close percentiles)"):
    tbl = fc.median.copy()
    for p in (10, 25, 75, 90):
        tbl[f"close_p{p}"] = fc.q[p]
    st.dataframe(tbl, width="stretch")

st.caption(
    f"{len(df)} candles loaded · lookback {lookback_used} · inference {elapsed:.1f}s on CPU "
    f"(cached reruns are instant) · Model weights: [NeoQuasar on Hugging Face](https://huggingface.co/NeoQuasar). "
    "Kronos model code vendored under `kronos_vendor/` (MIT, © 2025 ShiYu)."
)
