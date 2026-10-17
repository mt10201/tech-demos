"""Backtest: buy any Bitcoin Up or Down side once it trades at <= threshold, hold to resolution.

Read-only, public endpoints only:
  Gamma  /events (closed, tag bitcoin, sliding end-date windows)
  CLOB   /prices-history (startTs/endTs, fidelity=1 -> ~1-minute points; finest the API returns)
  Data   /trades?market=<conditionId> (taker fills; used for the 'realistic fill' variant)

Usage:  python backtest.py --days 30 --trade-sample 400
Writes: data/backtest_results.json (summary used by the app's Backtest tab)
Raw caches go to $BT_CACHE (default ./.cache, git-ignored).
"""
from __future__ import annotations
import argparse, json, math, os, random, re, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

GAMMA, CLOB, DATA = "https://gamma-api.polymarket.com", "https://clob.polymarket.com", "https://data-api.polymarket.com"
THRESHOLDS = [0.01, 0.02, 0.03, 0.05]
CLOSE_BUFFER = 15  # seconds before close excluded
HERE = Path(__file__).parent
CACHE = Path(os.environ.get("BT_CACHE", HERE / ".cache"))
S = requests.Session(); S.headers["User-Agent"] = "penny-scanner-backtest/0.1"


def get(url, params, tries=5):
    for i in range(tries):
        try:
            r = S.get(url, params=params, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(1.5 * (i + 1)); continue
            r.raise_for_status(); return r.json()
        except requests.RequestException:
            time.sleep(1.5 * (i + 1))
    return None


# ---------- pure helpers (tested) ----------
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0: return (0.0, 1.0)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def ev_per_dollar(won: bool, price: float) -> float:
    """Return on $1 staked at `price`: +1/price-1 if win else -1."""
    return (1 / price - 1) if won else -1.0


_T = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([AP]M)", re.I)

def duration_label(title: str) -> str:
    times = _T.findall(title.split(" - ", 1)[-1])
    if len(times) >= 2:
        mins = [((int(h) % 12) + (12 if ap.upper() == "PM" else 0)) * 60 + int(m or 0) for h, m, ap in times[:2]]
        d = (mins[1] - mins[0]) % 1440
        return {5: "5m", 15: "15m", 60: "1h", 240: "4h"}.get(d, f"{d}m")
    return "1h" if len(times) == 1 else "daily/other"


# ---------- data collection ----------
def collect_markets(days: int) -> list[dict]:
    f = CACHE / f"markets_{days}d.json"
    if f.exists(): return json.loads(f.read_text())
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    windows = []
    t = end
    while t > end - timedelta(days=days):
        windows.append((t - timedelta(hours=2), t)); t -= timedelta(hours=2)

    def win(w):
        out, off = [], 0
        while True:
            d = get(f"{GAMMA}/events", {"closed": "true", "tag_slug": "bitcoin", "limit": 100, "offset": off,
                                        "end_date_min": w[0].isoformat().replace("+00:00", "Z"),
                                        "end_date_max": w[1].isoformat().replace("+00:00", "Z")})
            if not d: break
            out += d
            if len(d) < 100: break
            off += 100
        return out

    seen, mk = set(), []
    with ThreadPoolExecutor(8) as ex:
        for evs in ex.map(win, windows):
            for e in evs:
                if "Up or Down" not in e.get("title", ""): continue
                for m in e.get("markets", []):
                    cid = m.get("conditionId")
                    if not cid or cid in seen: continue
                    try:
                        prices = [float(x) for x in json.loads(m["outcomePrices"])]
                        toks = json.loads(m["clobTokenIds"]); outs = json.loads(m["outcomes"])
                    except Exception: continue
                    if sorted(prices) != [0.0, 1.0]: continue  # unresolved / voided
                    seen.add(cid)
                    mk.append({"title": e["title"], "cid": cid, "end": m.get("endDate") or e["endDate"],
                               "dur": duration_label(e["title"]), "tokens": toks, "outcomes": outs, "prices": prices})
    f.write_text(json.dumps(mk)); return mk


def side_min_price(token: str, end_ts: int) -> float | None:
    d = get(f"{CLOB}/prices-history", {"market": token, "startTs": end_ts - 6 * 3600, "endTs": end_ts, "fidelity": 1})
    if not d: return None
    pts = [p["p"] for p in d.get("history", []) if p["t"] < end_ts - CLOSE_BUFFER]
    return min(pts) if pts else None


def first_fills(cid: str, end_ts: int) -> dict:
    """token -> {thr: (price of first taker fill <= thr, shares at <= thr)} before close-buffer."""
    trades, off = [], 0
    while True:
        d = get(f"{DATA}/trades", {"market": cid, "limit": 10000, "offset": off})
        if not d: break
        trades += d
        if len(d) < 10000: break
        off += 10000
    trades = sorted((t for t in trades if t["timestamp"] < end_ts - CLOSE_BUFFER), key=lambda t: t["timestamp"])
    out = defaultdict(dict)
    for t in trades:  # chronological: first fill at <= thr is the entry
        for thr in THRESHOLDS:
            if t["price"] <= thr and thr not in out[t["asset"]]:
                out[t["asset"]][thr] = [t["price"], 0.0]
    for t in trades:  # shares printed at <= thr (liquidity proxy)
        for thr, v in out.get(t["asset"], {}).items():
            if t["price"] <= thr: v[1] += t["size"]
    return {k: v for k, v in out.items()}


def ts(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


# ---------- aggregation ----------
def summarize(rows: list[dict], price_key: str) -> list[dict]:
    """rows: {'dur','thr','won', price_key} -> per (thr,dur) stats; dur 'all' included."""
    g = defaultdict(list)
    for r in rows:
        g[(r["thr"], r["dur"])].append(r); g[(r["thr"], "all")].append(r)
    out = []
    for (thr, dur), rs in sorted(g.items()):
        n, k = len(rs), sum(r["won"] for r in rs)
        lo, hi = wilson(k, n)
        evs = [ev_per_dollar(r["won"], r[price_key]) for r in rs]
        avg_p = sum(r[price_key] for r in rs) / n
        out.append({"threshold_c": round(thr * 100), "duration": dur, "sides": n, "wins": k, "win_rate": k / n,
                    "ci_low": lo, "ci_high": hi, "avg_entry_c": avg_p * 100, "breakeven": avg_p,
                    "ev_per_$1": sum(evs) / n, "total_pnl_$1_each": sum(evs)})
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--trade-sample", type=int, default=400, help="max touched markets per duration for trade fills")
    ap.add_argument("--workers", type=int, default=16); a = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    t0 = time.time(); mk = collect_markets(a.days); print(f"{len(mk)} resolved markets in {time.time()-t0:.0f}s")

    hf = CACHE / f"minprice_{a.days}d.json"
    mins = json.loads(hf.read_text()) if hf.exists() else {}
    jobs = [(m, i) for m in mk for i in range(2) if f"{m['cid']}:{i}" not in mins]
    with ThreadPoolExecutor(a.workers) as ex:
        for (m, i), v in zip(jobs, ex.map(lambda j: side_min_price(j[0]["tokens"][j[1]], ts(j[0]["end"])), jobs)):
            mins[f"{m['cid']}:{i}"] = v
    hf.write_text(json.dumps(mins)); print(f"price histories done {time.time()-t0:.0f}s")

    rows, gaps = [], 0
    for m in mk:
        for i in range(2):
            lo = mins.get(f"{m['cid']}:{i}")
            if lo is None: gaps += 1; continue
            for thr in THRESHOLDS:
                if 0 < lo <= thr:
                    rows.append({"cid": m["cid"], "i": i, "dur": m["dur"], "thr": thr, "won": m["prices"][i] == 1.0,
                                 "entry": thr, "end": m["end"]})

    # realistic variant: sample markets that touched <= max threshold, per duration
    random.seed(7)
    touched = defaultdict(set)
    for r in rows: touched[r["dur"]].add(r["cid"])
    sample = {c for d, cs in touched.items() for c in random.sample(sorted(cs), min(a.trade_sample, len(cs)))}
    by_cid = {m["cid"]: m for m in mk}
    tf = CACHE / f"fills_{a.days}d.json"
    fills = json.loads(tf.read_text()) if tf.exists() else {}
    todo = [c for c in sample if c not in fills]
    with ThreadPoolExecutor(8) as ex:
        for c, v in zip(todo, ex.map(lambda c: first_fills(c, ts(by_cid[c]["end"])), todo)):
            fills[c] = {tok: {str(k): x for k, x in d.items()} for tok, d in v.items()}
    tf.write_text(json.dumps(fills)); print(f"trades done {time.time()-t0:.0f}s ({len(sample)} markets)")

    real, sampled_touch, no_fill = [], 0, 0
    for r in rows:
        if r["cid"] not in sample: continue
        sampled_touch += 1
        tok = by_cid[r["cid"]]["tokens"][r["i"]]
        f = fills[r["cid"]].get(tok, {}).get(str(r["thr"]))
        if not f: no_fill += 1; continue
        real.append({**r, "fill": max(f[0], 0.001), "fill_shares": f[1]})

    ends = sorted(m["end"] for m in mk)
    dur_counts = defaultdict(int)
    for m in mk: dur_counts[m["dur"]] += 1
    res = {"generated": datetime.now(timezone.utc).isoformat(), "days": a.days, "markets": len(mk),
           "markets_by_duration": dict(dur_counts), "range": [ends[0], ends[-1]], "history_gaps_sides": gaps,
           "close_buffer_s": CLOSE_BUFFER, "price_history_fidelity": "1 minute",
           "touch": summarize(rows, "entry"),
           "realistic": summarize(real, "fill") if real else [],
           "realistic_meta": {"sampled_markets": len(sample), "touch_rows_in_sample": sampled_touch,
                              "touch_rows_without_fill": no_fill,
                              "median_fill_shares": sorted(r["fill_shares"] for r in real)[len(real)//2] if real else None}}
    out = HERE / "data" / "backtest_results.json"; out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(res, indent=1)); print(f"wrote {out} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
