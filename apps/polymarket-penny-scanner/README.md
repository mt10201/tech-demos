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

## Notes
- "Price" in the scanner is Gamma's `outcomePrices` (midpoint-ish); the depth panel shows real CLOB bids/asks.
- History "touched" = 1-minute price history dipped to the threshold; that doesn't mean a fill was available.
- Media: `media/screenshot.png`, `media/history.png`, `media/demo.webm` (recorded with `capture.py`, needs `pip install playwright && playwright install chromium`).
