"""Band backtest: the price ranges where wallet 0x50f7 actually profits.

Low bands (buy a side the first time it trades into the band): 5-10c, 10-15c, 15-20c.
Near-sure bands (buy the favourite the first time it reaches the band): 80-90c, 90-95c, 95-99c,
optionally only in the final N minutes before close (any / last 5 / last 2 / last 1 min).

Two models, same data as backtest.py (reuses its market cache):
  touch     CLOB /prices-history (1-minute points), entry at that point's price
  realistic data-api /trades taker fills (random sample per duration), entry at the first fill in band
Both exclude anything in the final 15 s. EV is shown gross and after the crypto taker fee
(fee = shares x 0.07 x p x (1-p), i.e. 0.07 x (1-p) per $1 staked).
Also: tail risk for the near-sure bands ($100 fixed stake, chronological), and the wallet's own
results per band from /closed-positions plus entry timing from /activity.

Usage: python backtest_bands.py --days 30 --trade-sample 400
Writes data/bands_results.json
"""
from __future__ import annotations
import argparse, gzip, json, random, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from backtest import CACHE, CLOB, DATA, CLOSE_BUFFER, collect_markets, get, ts, wilson, ev_per_dollar

HERE = Path(__file__).parent
DUR_S = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
LOW = [(0.05, 0.10), (0.10, 0.15), (0.15, 0.20)]          # lo < p <= hi
HIGH = [(0.80, 0.90), (0.90, 0.95), (0.95, 0.99)]         # lo <= p < hi
WINDOWS = {"any": None, "last 5m": 300, "last 2m": 120, "last 1m": 60}
FEE_RATE = 0.07
WALLET = "0xee65685de42f8de9a03b4c53ee77d56a20d2cfc9"
STAKE = 100.0


def in_band(p: float, band: tuple, low: bool) -> bool:
    lo, hi = band
    return lo < p <= hi if low else lo <= p < hi


def first_entry(points: list, end_ts: int, band: tuple, low: bool, window_s: int | None):
    """points: chronological [(t, p)]. Return (t, p) of the first point in band within the window, else None."""
    for t, p in points:
        if t >= end_ts - CLOSE_BUFFER: break
        if window_s is not None and t < end_ts - window_s: continue
        if in_band(p, band, low): return (t, p)
    return None


def fee_per_dollar(p: float) -> float:
    return FEE_RATE * (1 - p)


def tail_risk(bets: list[dict]) -> dict:
    """bets: {'t','won','price'} -> fixed-stake equity stats in chronological order."""
    eq = peak = mdd = 0.0; streak = worst = 0
    for b in sorted(bets, key=lambda b: b["t"]):
        pnl = STAKE * (1 / b["price"] - 1) if b["won"] else -STAKE
        eq += pnl; peak = max(peak, eq); mdd = max(mdd, peak - eq)
        streak = 0 if b["won"] else streak + 1; worst = max(worst, streak)
    return {"final_pnl_$": round(eq, 2), "max_drawdown_$": round(mdd, 2), "worst_losing_streak": worst}


def stats(bets: list[dict]) -> dict:
    n = len(bets); k = sum(b["won"] for b in bets); lo, hi = wilson(k, n)
    avg = sum(b["price"] for b in bets) / n
    ev = sum(ev_per_dollar(b["won"], b["price"]) for b in bets) / n
    fee = sum(fee_per_dollar(b["price"]) for b in bets) / n
    return {"sides": n, "wins": k, "win_rate": k / n, "ci_low": lo, "ci_high": hi, "avg_entry_c": avg * 100,
            "breakeven": avg, "ev_per_$1": ev, "ev_after_fee": ev - fee, **tail_risk(bets)}


# ---------------- data ----------------
def hist_points(token: str, end_ts: int, dur: str) -> list:
    d = get(f"{CLOB}/prices-history", {"market": token, "startTs": end_ts - DUR_S[dur] - 300, "endTs": end_ts, "fidelity": 1})
    return [(p["t"], p["p"]) for p in (d or {}).get("history", [])]


def trades(cid: str) -> tuple[list, bool]:
    out, off, ok = [], 0, True
    while True:
        d = get(f"{DATA}/trades", {"market": cid, "limit": 10000, "offset": off})
        if d is None: ok = False; break
        out += [(t["timestamp"], t["asset"], t["price"]) for t in d]
        if len(d) < 10000: break
        off += 10000
    return sorted(out), ok


def load_gz(f: Path):
    return json.loads(gzip.decompress(f.read_bytes())) if f.exists() else {}


def save_gz(f: Path, obj):
    f.write_bytes(gzip.compress(json.dumps(obj).encode()))


def wallet_section(by_cid: dict) -> dict:
    pos = json.loads((CACHE / "wallet_closed.json").read_text())
    btc = [p for p in pos if p["title"].startswith("Bitcoin Up or Down")]
    bands = [("5-10", 0.05, 0.10), ("10-15", 0.10, 0.15), ("15-20", 0.15, 0.20),
             ("80-90", 0.80, 0.90), ("90-95", 0.90, 0.95), ("95-99", 0.95, 0.99), ("99-100", 0.99, 1.0)]
    af = CACHE / "wallet_activity.json.gz"; act = load_gz(af)
    random.seed(11)
    rows = []
    for name, lo, hi in bands:
        s = [p for p in btc if lo < p["avgPrice"] <= hi]
        if not s: rows.append({"band_c": name, "positions": 0}); continue
        k = sum(p["curPrice"] == 1 for p in s); ci = wilson(k, len(s))
        cost = sum(p["avgPrice"] * p["totalBought"] for p in s)
        # entry timing from /activity on a sample of positions
        samp = random.sample(s, min(150, len(s)))
        todo = [p["conditionId"] for p in samp if p["conditionId"] not in act]
        with ThreadPoolExecutor(8) as ex:
            for c, d in zip(todo, ex.map(lambda c: get(f"{DATA}/activity", {"user": WALLET, "market": c, "type": "TRADE", "limit": 500}), todo)):
                act[c] = [(x["timestamp"], x["side"], x["price"], x["usdcSize"], x["slug"]) for x in (d or [])]
        secs = []
        for p in samp:
            buys = [a for a in act.get(p["conditionId"], []) if a[1] == "BUY"]
            m = by_cid.get(p["conditionId"])
            end = ts(m["end"]) if m else None
            if end is None and buys and "-updown-" in buys[0][4]:
                parts = buys[0][4].split("-"); end = int(parts[-1]) + {"5m": 300, "15m": 900, "4h": 14400}.get(parts[2], 0)
            if end:
                usd = sum(a[3] for a in buys) or 1
                secs.append(sum((end - a[0]) * a[3] for a in buys) / usd if buys else None)
        secs = sorted(x for x in secs if x is not None)
        med = secs[len(secs) // 2] if secs else None
        rows.append({"band_c": name, "positions": len(s), "wins": k, "win_rate": k / len(s), "ci_low": ci[0], "ci_high": ci[1],
                     "cost_$": round(cost), "realized_pnl_$": round(sum(p["realizedPnl"] for p in s)),
                     "return_on_cost": sum(p["realizedPnl"] for p in s) / cost if cost else None,
                     "median_s_before_close": med, "timing_sample": len(secs),
                     "share_last_60s": sum(x <= 60 for x in secs) / len(secs) if secs else None})
    save_gz(af, act)
    return {"wallet": WALLET, "range": [pos[-1]["endDate"], pos[0]["endDate"]], "bands": rows}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--trade-sample", type=int, default=400); a = ap.parse_args()
    t0 = time.time()
    mk = [m for m in collect_markets(a.days) if m["dur"] in DUR_S]
    by_cid = {m["cid"]: m for m in mk}
    hf = CACHE / f"hist_full_{a.days}d.json.gz"; H = load_gz(hf)
    jobs = [(m, i) for m in mk for i in range(2) if f"{m['cid']}:{i}" not in H]
    with ThreadPoolExecutor(16) as ex:
        for (m, i), v in zip(jobs, ex.map(lambda j: hist_points(j[0]["tokens"][j[1]], ts(j[0]["end"]), j[0]["dur"]), jobs)):
            H[f"{m['cid']}:{i}"] = v
    save_gz(hf, H); print(f"histories {len(H)} in {time.time()-t0:.0f}s", flush=True)

    random.seed(7)
    per = defaultdict(list)
    for m in mk: per[m["dur"]].append(m["cid"])
    sample = [c for d, cs in per.items() for c in random.sample(sorted(cs), min(a.trade_sample, len(cs)))]
    tf = CACHE / f"trades_bands_{a.days}d.json.gz"; T = load_gz(tf)
    todo = [c for c in sample if c not in T]
    with ThreadPoolExecutor(8) as ex:
        for c, (tr, ok) in zip(todo, ex.map(trades, todo)):
            T[c] = {"ok": ok, "trades": tr}
    save_gz(tf, T); print(f"trades {len(sample)} markets in {time.time()-t0:.0f}s", flush=True)

    specs = [("low", b, "any") for b in LOW] + [("high", b, w) for b in HIGH for w in WINDOWS]
    out = {"touch": [], "realistic": []}
    for model in ("touch", "realistic"):
        for kind, band, win in specs:
            bets = defaultdict(list)
            for m in (mk if model == "touch" else [by_cid[c] for c in sample]):
                end = ts(m["end"])
                for i, tok in enumerate(m["tokens"]):
                    if model == "touch":
                        pts = H.get(f"{m['cid']}:{i}") or []
                    else:
                        pts = [(t, p) for t, asset, p in T[m["cid"]]["trades"] if asset == tok]
                    e = first_entry(pts, end, band, kind == "low", WINDOWS[win])
                    if e: bets[m["dur"]].append({"t": e[0], "price": max(e[1], 0.001), "won": m["prices"][i] == 1.0})
            allb = [b for v in bets.values() for b in v]
            for dur, bs in [("all", allb)] + sorted(bets.items()):
                if bs:
                    out[model].append({"band_c": f"{band[0]*100:g}-{band[1]*100:g}", "kind": kind, "window": win,
                                       "duration": dur, **stats(bs)})
    res = {"generated": datetime.now(timezone.utc).isoformat(), "markets": len(mk),
           "trade_sample_markets": len(sample), "trade_fetch_failures": sum(not T[c]["ok"] for c in sample),
           "fee_rate": FEE_RATE, "stake_$": STAKE, **out, "wallet": wallet_section(by_cid)}
    f = HERE / "data" / "bands_results.json"; f.write_text(json.dumps(res, indent=1)); print(f"wrote {f} {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
