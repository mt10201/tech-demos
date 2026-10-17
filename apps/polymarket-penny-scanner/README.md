# Polymarket penny-side scanner

Read-only Streamlit app that scans live Polymarket **Bitcoin Up or Down** markets for sides priced at or below a threshold (default 2¢), shows time to close and CLOB order-book depth, includes a payoff calculator, and checks recent resolved markets to see how often penny sides actually won.

No wallet, no API keys, no trading. Uses only public endpoints:
- Gamma `GET https://gamma-api.polymarket.com/events` (tag `bitcoin`, filtered to "Up or Down")
- CLOB `GET https://clob.polymarket.com/book?token_id=…`
- CLOB `GET https://clob.polymarket.com/prices-history?market=…&interval=1d&fidelity=1`

## Run
```bash
cd apps/polymarket-penny-scanner
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py        # opens http://localhost:8501
pytest -q                   # tests for payoff math + threshold filter
```

## Backtest (Backtest tab)
```bash
python backtest.py --days 30 --trade-sample 400   # ~5 min; writes data/backtest_results.json
python wallet_check.py                             # ~3 min; writes data/wallet_check.json
```
- Markets: Gamma `/events?closed=true&tag_slug=bitcoin` in 2-hour end-date windows (offset pagination is capped at ~5000, so windows are used instead), filtered to "Up or Down" markets that resolved 1/0.
- **Touch model:** CLOB `/prices-history?startTs&endTs&fidelity=1` (1-minute points, the finest the API returns); a side "touched" a threshold if any point more than 15 s before close was ≤ it. Entry is assumed at exactly the threshold.
- **Realistic-fill model:** for a random sample of touched markets (≤ N per duration), data-api `/trades?market=<conditionId>` taker fills; the side must have an actual trade ≤ threshold more than 15 s before close, and entry is that first trade's price.
- **EV per $1:** `+1/price − 1` if the side won, `−1` otherwise, averaged. 95% CIs are Wilson intervals on the win rate.
- **Wallet check:** the "$604K" wallet in the bookmarked post is Polymarket user `0x50f7` (proxy wallet `0xee65…cfc9`). The script reads its all-time leaderboard row and its most recent 20,000 closed positions, then buckets the Bitcoin Up or Down ones by average entry price.
- Caches live in `.cache/` (git-ignored; override with `BT_CACHE=`).

## Notes
- "Price" in the scanner is Gamma's `outcomePrices` (midpoint-ish); the depth panel shows real CLOB bids/asks.
- History "touched" = 1-minute price history dipped to the threshold; that doesn't mean a fill was available.
- Media: `media/screenshot.png`, `media/history.png`, `media/backtest.png`, `media/backtest_wallet.png`, `media/demo.webm` (recorded with `capture.py`, needs `pip install playwright && playwright install chromium`).
