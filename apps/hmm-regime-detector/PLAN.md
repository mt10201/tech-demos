# PLAN: hmm-regime-detector

Source: X bookmark (2026-09-22, surfaced 2026-10-22) https://x.com/0xTrackmind/status/2102413376148095032
Context threads:
- Out-of-sample regime testing: https://x.com/quantpedia/status/2110290912932667854
- `hmmlearn` smoother look-ahead warning: https://x.com/XARC_Real/status/2111711030208524330
Upstream library: [`hmmlearn`](https://github.com/hmmlearn/hmmlearn) (BSD-3-Clause)

## Goal
Detect calm risk-on vs. stressed risk-off market regimes with a Gaussian Hidden Markov Model (`hmmlearn`), eliminate `predict_proba` look-ahead bias via a causal forward-only (`alpha`) filter and expanding-window walk-forward refits, backtest a regime-switching allocation across equities (`SPY`) and defensive assets (`TLT`, `GLD`), and export daily regime probabilities and target weights as a CSV for downstream portfolio bots.

## MVP scope (single user, CPU-only, Windows-friendly)
- **Data ingestion (`hmm_demo/data.py`):** Pull adjusted daily close prices via `yfinance` for a primary equity/risk asset (default `SPY`, custom ticker option) and two defensive assets (default `TLT` and `GLD`, customizable) over a selectable window (`5y`, `10y`, `15y`, `max`). Includes a bundled cached/synthetic multi-regime fallback dataset so offline runs and unit tests need no network.
- **Feature engineering & deterministic HMM fit (`hmm_demo/model.py`):**
  - Compute daily log returns and rolling annualized realized volatility (configurable window, default 20 trading days).
  - Fit `hmmlearn.hmm.GaussianHMM` with 2 to 4 states (default 3: `Bull / Calm`, `Neutral / Transition`, `Bear / High-Vol`).
  - Deterministically sort states by ascending realized volatility (`means_[:, 1]`) and permute `startprob_`, `transmat_`, `means_`, and `covars_` in place so state 0 is always lowest-volatility risk-on and state K-1 is highest-volatility risk-off across refits.
- **Look-ahead bias prevention (`hmm_demo/model.py`):**
  - Implement causal **forward-only filtering** (`alpha` recursion in log-space using `startprob_`, `transmat_`, and `_compute_log_likelihood`) where $P(S_t \mid X_{1:t})$ uses zero future data.
  - Implement **expanding-window walk-forward refitting + forward filtering** (periodic refit on $X_{1:t}$ after an initial training warmup) for strictly out-of-sample regime probabilities.
  - Provide a side-by-side comparison and UI toggle against `hmmlearn`'s full-sample `predict_proba` (forward-backward smoother $P(S_t \mid X_{1:T})$) to quantify look-ahead leakage.
- **Walk-forward regime allocation backtest (`hmm_demo/backtest.py`):**
  - Allocate for day $t$ return using only regime state or probability-weighted target weights known at the close of day $t-1$ (strictly 1-day lagged signal, zero look-ahead), with configurable per-regime weights (e.g. Bull -> 100% SPY, Neutral -> 50% SPY / 25% TLT / 25% GLD, Bear -> 50% TLT / 50% GLD) and transaction cost in basis points.
  - Compare against Buy-and-Hold primary asset (`SPY`), a static `60/40` (`60% SPY / 40% TLT`) benchmark, and the look-ahead smoothed HMM upper bound.
  - Compute CAGR, annualized volatility, Sharpe, Sortino, Max Drawdown, Calmar ratio, annualized turnover, and per-regime summary statistics (annualized return, vol, Sharpe, average regime duration in trading days, % of time).
- **Interactive visualizations (`hmm_demo/charts.py`) & UI (`app.py`):**
  1. Primary asset price chart shaded by active regime + stacked daily regime probability chart.
  2. Transition probability matrix heatmap + per-regime summary table + forward-only vs. smoother discrepancy chart.
  3. Walk-forward equity curve & underwater drawdown chart vs. benchmarks + performance table.
  4. One-click CSV export of daily dates, prices, features, causal regime state, forward-filtered probabilities, and target portfolio weights for `@Portfolio Oversight` and `@Strategy Research`.
  5. Clear research-only disclaimer (not financial advice, no live trading).

### Explicit outs
- No brokerage connections, API keys, or live order execution.
- No intraday/tick data or options/futures pricing.
- No deep-learning hybrids; strictly Gaussian HMMs via `hmmlearn`.

## Vertical slices / tasks
1. `hmm_demo/data.py`: Fetch and align daily prices via `yfinance` (`threads=False`), bundle a realistic offline fallback dataset, and compute log returns + rolling annualized volatility.
2. `hmm_demo/model.py`: Fit `GaussianHMM`, sort states by volatility in place, compute causal forward-only (`alpha`) probabilities, run expanding-window walk-forward refits, and compute per-regime stats + expected durations.
3. `hmm_demo/backtest.py`: Run the 1-day-lagged walk-forward allocation backtest (hard state or probability-blended weights) with transaction costs, benchmarks, performance metrics, and bot-ready CSV builder.
4. `hmm_demo/charts.py`: Build Plotly figures for regime-shaded price + probabilities, transition heatmap + look-ahead comparison, and equity curves + drawdowns.
5. `app.py`: Streamlit interface with sidebar controls, three organized visual sections, look-ahead audit toggle, CSV export button, and disclaimer.
6. `tests/`: `pytest` suite verifying feature calculation, deterministic volatility state sorting, causal forward-only invariance to future data perturbations (vs. smoother leakage), backtest $t-1 \to t$ no-lookahead property, and CSV export schema.
7. `media/`: Capture 3 high-resolution screenshots of the running Streamlit app (`01-regime-shaded-price.png`, `02-walkforward-backtest.png`, `03-transition-and-stats.png`).

## Stack (one line each)
- **Streamlit**: Single-file interactive local dashboard consistent with the monorepo demos.
- **hmmlearn**: Standard BSD-licensed Gaussian Hidden Markov Model implementation in Python.
- **scikit-learn / scipy**: Numerically stable log-space filtering (`logsumexp`) and covariance utilities.
- **pandas / numpy**: Time-series alignment, rolling volatility features, and vectorized backtest accounting.
- **yfinance**: Free adjusted daily ETF/equity price history with no API key required.
- **Plotly**: Interactive regime-shaded price charts, stacked probability bands, heatmaps, and equity curves.
- **pytest**: Fast unit tests for the core mathematical and no-lookahead invariants.

## Folder structure
```
apps/hmm-regime-detector/
  app.py
  PLAN.md
  README.md
  requirements.txt
  hmm_demo/
    __init__.py
    data.py
    model.py
    backtest.py
    charts.py
    sample_prices.csv
  tests/
    test_hmm_regime.py
  media/
    01-regime-shaded-price.png
    02-walkforward-backtest.png
    03-transition-and-stats.png
```

## Deferred
- Multivariate cross-asset emission features (yield curve slope, VIX term structure, credit spreads).
- Sticky HDP-HMM (non-parametric state count inference) and Student-t emission distributions.
- Intraday bar support and automated scheduled webhook export.
