"""Read-only check of the wallet promoted in the @PolyDekos post (Polymarket username '0x50f7').

Uses public data-api endpoints: /v1/leaderboard (all-time PnL/volume) and /closed-positions
(most recent N closed positions). Buckets Bitcoin Up or Down positions by average entry price.
Usage: python wallet_check.py [--max 20000]
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import requests
from backtest import wilson

WALLET = "0xee65685de42f8de9a03b4c53ee77d56a20d2cfc9"  # proxyWallet for username 0x50f7 (gamma public-search)
DATA = "https://data-api.polymarket.com"
BUCKETS = [(0, 0.01), (0.01, 0.02), (0.02, 0.05), (0.05, 0.20), (0.20, 0.80), (0.80, 1.0)]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--max", type=int, default=20000); a = ap.parse_args()
    lb = requests.get(f"{DATA}/v1/leaderboard", params={"user": WALLET, "timePeriod": "ALL", "orderBy": "PNL"}, timeout=30).json()
    pos, off = [], 0
    while off < a.max:
        d = requests.get(f"{DATA}/closed-positions", params={"user": WALLET, "limit": 50, "offset": off,
                         "sortBy": "TIMESTAMP", "sortDirection": "DESC"}, timeout=30).json()
        if not d: break
        pos += d; off += 50
    btc = [p for p in pos if p["title"].startswith("Bitcoin Up or Down")]
    rows = []
    for lo, hi in BUCKETS:
        s = [p for p in btc if lo < p["avgPrice"] <= hi]
        k = sum(p["curPrice"] == 1 for p in s)
        cost = sum(p["avgPrice"] * p["totalBought"] for p in s)
        ci = wilson(k, len(s))
        rows.append({"entry_bucket_c": f"{lo*100:g}-{hi*100:g}", "positions": len(s), "wins": k,
                     "win_rate": k / len(s) if s else None, "ci_low": ci[0], "ci_high": ci[1],
                     "cost_$": round(cost), "realized_pnl_$": round(sum(p["realizedPnl"] for p in s))})
    top = sorted(btc, key=lambda p: -p["realizedPnl"])[:5]
    res = {"wallet": WALLET, "username": "0x50f7", "leaderboard_all_time": lb[0] if lb else None,
           "closed_positions_fetched": len(pos), "range": [pos[-1]["endDate"], pos[0]["endDate"]] if pos else None,
           "btc_updown_positions": len(btc), "btc_updown_pnl_$": round(sum(p["realizedPnl"] for p in btc)),
           "all_pnl_in_window_$": round(sum(p["realizedPnl"] for p in pos)),
           "buckets": rows,
           "top_btc_trades": [{k: p[k] for k in ("title", "outcome", "avgPrice", "totalBought", "realizedPnl")} for p in top]}
    out = Path(__file__).parent / "data" / "wallet_check.json"; out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(res, indent=1)); print(json.dumps({k: v for k, v in res.items() if k != "buckets"}, indent=1))


if __name__ == "__main__":
    main()
