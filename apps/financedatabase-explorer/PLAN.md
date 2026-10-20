# PLAN — financedatabase-explorer

**Goal:** A single-page "Global Asset Universe Explorer" that lets one user browse and filter
the 300k+ symbols in [FinanceDatabase](https://github.com/JerBouma/FinanceDatabase) (`pip install financedatabase`) without writing code.

Source bookmark: https://x.com/Smartpigai/status/2098967844314861802 (2026-09-13).

## MVP scope (single user, local)
- Pick an asset class: Equities, ETFs, Funds, Indices, Cryptos, Currencies, Money Markets.
- Cascading filters built from the class's own option fields (each list only shows values that
  still exist after the filters above it): country → sector → industry group → industry → exchange
  → market-cap band for equities; category group → category → family → exchange for ETFs/Funds, etc.
- Search: fuzzy match on symbol/name (typo tolerant, RapidFuzz) plus all-words match in the summary.
- Results table with a live count and CSV download.
- Plotly treemap of the filtered set (sector → industry group → industry, or the class's
  category hierarchy) and a bar chart of the top countries/exchanges.
- `st.cache_data` for the loaded class; friendly error + retry when the first-run download fails (offline).

**Out:** prices/quotes, fundamentals (FinanceToolkit needs an API key), watchlists, accounts,
trading of any kind, deployment.

## Vertical slices
1. `data.py` — load a class via FinanceDatabase, normalise to a plain DataFrame (symbol column), wrap download errors.
2. `explorer.py` — pure-pandas filter/option/search/aggregation logic + per-class config (unit-tested, no Streamlit).
3. `app.py` — Streamlit UI: sidebar class + cascading multiselects + search; metrics, charts, table, CSV.
4. `capture.py` — headless Streamlit + Playwright screenshots into `media/`.

## Stack
- **financedatabase** — the technology being demoed; ships the data and option lists.
- **Streamlit** — one-file UI, built-in caching and download button.
- **Plotly Express** — treemap + bar in two calls.
- **RapidFuzz** — fast, wheel-installable fuzzy matching (Windows OK).
- **pytest** — tests only the filter/search logic.
- **Playwright** (dev only) — screenshots.

## Layout
```
apps/financedatabase-explorer/
  app.py          Streamlit UI
  data.py         loading + error wrapping
  explorer.py     filter / options / search / aggregation logic + ASSET_CLASSES config
  capture.py      screenshots (dev)
  tests/test_explorer.py
  media/          screenshots
  requirements.txt, requirements-dev.txt, README.md, PLAN.md
```

## Deferred
- Price sparkline per symbol (yfinance/FinanceToolkit), saved filter presets, map view by country,
  comparing two filtered universes side by side.
