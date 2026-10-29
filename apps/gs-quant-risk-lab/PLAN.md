# gs-quant Risk Lab: plan

## Goal
An offline Streamlit risk lab that uses Goldman Sachs' open-source `gs_quant.timeseries` (no Marquee login) plus
standard fat-tail statistics to compare ETFs and strategy-sleeve return streams side by side, for Portfolio
Oversight's diversification and tail-risk checks.

## Pre-build check (done 2026-10-29)
`gs-quant==2.2.3` in a fresh Python 3.13 venv, no `GS_CLIENT_ID`/`GS_CLIENT_SECRET`, and with networking disabled
(`unshare -n`): `volatility`, `max_drawdown`, `correlation`, `beta`, `zscores`, `returns` all run on plain pandas
Series. `drawdown_length` is a Marquee report call and is **not** used (duration is computed locally).

## MVP scope (single user, local)
- Data: yfinance daily adjusted closes (default SPY/TLT/GLD; preset with the sleeves' ETFs SPYM, SCHF, SCHE, SPTL,
  VGIT, SCHP, IAU, SIVR, PDBC, USO, SLV, GLD) and an optional CSV of daily sleeve returns (`date,sleeve,return`)
  with a bundled **synthetic** sample.
- Rolling panel (gs_quant): trailing vol, drawdown, z-scores, rolling beta to SPY/TLT/GLD.
- Fat-tail panel: excess kurtosis, Hill tail index + stability plot across k, historical and block-bootstrap
  CVaR 95/99, max drawdown and drawdown duration, optional stable-alpha (McCulloch quantile fit) vs Gaussian.
- Correlation panel: full-sample matrix, rolling 63-day correlation (gs_quant), stress-only correlation on days
  SPY falls more than 2%.
- Every table has a CSV download. Annualization labelled per series: 252 (exchange-traded) vs 365 (series with
  weekend observations, e.g. crypto); user can override.

## Explicit outs
- No broker code, no Alpaca keys, no order logic. Research only.
- No Marquee / GS pricing or risk models. No intraday data. No portfolio optimisation.

## Vertical slices / tasks
1. `risklab/data.py`: yfinance loader, sleeve CSV parser/validator, merge into one returns frame, annualization detection.
2. `risklab/analytics.py`: gs_quant wrappers (trailing windows only, `Window(w, w)` so partial windows are dropped).
3. `risklab/tails.py`: kurtosis, Hill estimator, historical/bootstrap CVaR, drawdown duration, stable fit.
4. `app.py`: sidebar inputs, four tabs, Plotly charts, CSV export buttons, disclaimer.
5. Tests: no-look-ahead (truncation invariance), Hill/CVaR on known distributions, CSV validation, drawdown duration.
6. Screenshots + short video in `media/`, README with Windows run steps.

## Folder structure
```
apps/gs-quant-risk-lab/
  app.py               Streamlit UI
  risklab/data.py      loading + validation
  risklab/analytics.py gs_quant rolling metrics
  risklab/tails.py     fat-tail statistics
  risklab/sample_sleeves.csv  synthetic sample (not real strategy results)
  tests/               pytest (offline, synthetic data)
  media/               screenshots + video
  PLAN.md README.md requirements.txt
```

## Stack
- Streamlit: default UI for repo demos, fast to iterate.
- gs-quant (pinned 2.2.3): the technology being demoed; its timeseries module is pure pandas.
- yfinance: free daily prices, already used by other demos.
- scipy: kurtosis and stable-distribution fit.
- Plotly: interactive charts in Streamlit.
- pytest: critical-logic tests only.

## Deferred
- Multi-factor (joint) betas, regime-conditional stats (HMM demo CSV), EVT/GPD fits, intraday data,
  automatic feeds from paper-account equity curves.
