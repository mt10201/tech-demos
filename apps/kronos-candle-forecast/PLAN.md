# PLAN: kronos-candle-forecast

Source: X bookmark (2026-10-21) https://x.com/carm1nee/status/2112335978165583977
Upstream: https://github.com/shiyu-coder/Kronos (MIT, AAAI 2026)

## Goal
Show, in one local Streamlit page, what the open-source Kronos candlestick foundation
model forecasts for the next N candles of a real stock or crypto pair, with an
uncertainty band, and how well it did on past data.

## MVP scope (single user, CPU-only, Windows-friendly)
- Pick a market: stock/ETF ticker (yfinance) or crypto pair (ccxt public OHLCV from
  Kraken / Coinbase / OKX, with yfinance `BTC-USD` style as fallback).
- Pick interval (5m / 15m / 1h / 1d), lookback (context candles) and horizon N.
- Model size selector: Kronos-mini / Kronos-small (default) / Kronos-base, loaded
  from Hugging Face (NeoQuasar/*) and cached with `st.cache_resource`.
- Forecast mode: sample K independent paths, plot history candles + median forecast
  candles + 10-90 percentile close band (Plotly).
- Backtest/replay mode: pick a past cutoff, forecast from there, overlay the actual
  candles, show MAE / MAPE on close, directional accuracy and band coverage.
- Clear disclaimer: research/visualization only, not financial advice, no trading.

### Explicit outs
- No order placement, no API keys, no brokerage connection.
- No fine-tuning, no GPU-specific paths, no Kronos-large (not released).
- No live auto-refresh / animation (static chart -> screenshots only).

## Vertical slices / tasks
1. Data: `kronos_demo/data.py` fetches + cleans OHLCV into the Kronos column layout
   (`timestamps, open, high, low, close, volume, amount`) and builds future timestamps
   (24/7 for crypto, regular US session/business days for stocks).
2. Model: `kronos_demo/forecast.py` loads tokenizer+model, runs K sample paths via the
   upstream `KronosPredictor.predict_batch` (one row per path, so paths stay separate),
   returns median + quantiles.
3. Metrics: `kronos_demo/metrics.py` MAE, MAPE, directional accuracy, band coverage.
4. Chart: `kronos_demo/charts.py` Plotly candlestick + band + actual overlay.
5. UI: `app.py` sidebar controls, two modes, disclaimer, attribution.
6. Tests: pytest for data prep, future timestamps and metrics (no network, no model).
7. Screenshots: forecast view, backtest with actuals, crypto example -> `media/`.

## Stack (one line each)
- Streamlit: one-file UI, same as the other demos.
- Plotly: interactive candlesticks and filled bands.
- PyTorch CPU + upstream Kronos model code vendored in `kronos_vendor/` (the repo is
  not on PyPI; the README says to use its `model` package). MIT license kept.
- huggingface_hub / safetensors / einops: required by the upstream model code.
- yfinance: free stock/ETF/crypto candles, no key.
- ccxt: free public exchange OHLCV for crypto pairs, no key.
- pytest: tests for the critical pure logic only.

## Folder structure
```
apps/kronos-candle-forecast/
  app.py
  PLAN.md  README.md  requirements.txt
  kronos_demo/   __init__.py data.py forecast.py metrics.py charts.py
  kronos_vendor/ LICENSE NOTICE.md model/{__init__,kronos,module}.py   (upstream, MIT)
  tests/         test_data.py test_metrics.py
  media/         screenshots
```

## Deferred
- Multi-asset batch view, CSV upload, fine-tuning on own data, GPU toggle,
  saving forecasts to disk, walk-forward (rolling) backtest over many cutoffs.
