# Plan: Polymarket penny-side scanner

**Goal:** Let one user see, read-only, which live "Bitcoin Up or Down" Polymarket sides trade at ≤ N¢, and check how often such penny sides actually paid off.

## MVP (single user, local)
- Live list of open Bitcoin Up or Down markets (5m / 15m / hourly / 4h) with time to close.
- Flag any side whose best ask (or last price) is ≤ a user-set threshold (default 2¢).
- Order-book depth for a chosen side (top levels + $ notional at/under threshold).
- Payoff calculator: stake, price → shares, payout if it wins, profit, breakeven win rate.
- Resolved-history view: recent resolved markets, did a side ever trade ≤ threshold, and did it win.

## Outs (explicitly not doing)
- No wallet, no keys, no orders, no trading, no auth of any kind.
- No persistence/database, no alerts, no backtested strategy P&L.

## Tasks (vertical slices)
1. `polyapi.py`: Gamma `/events` (live + closed, tag `bitcoin`), CLOB `/book`, CLOB `/prices-history`.
2. `logic.py`: payoff math, threshold filter, history aggregation (unit-tested).
3. `app.py`: Streamlit UI with three tabs (Scanner, Payoff, History).
4. README with run steps; screenshot + video in `media/`.

## Stack
- Python 3.11+ — repo default.
- Streamlit — fastest documented way to a data UI, one file.
- requests — plain HTTP to public REST APIs; no SDK needed for read-only.
- pandas — tables in Streamlit.
- pytest — tests for payoff math and threshold filter only.
- Playwright (dev only) — headless screenshot + video capture.

## Folder layout
```
apps/polymarket-penny-scanner/
  PLAN.md README.md requirements.txt
  app.py polyapi.py logic.py
  tests/test_logic.py
  media/  (screenshot.png, demo.webm/mp4)
  capture.py (dev: Playwright recording)
```

## Deferred
- WebSocket live book updates; ETH/SOL Up-or-Down variants; fees modelling; longer history windows / caching to disk.
