"""Read-only wrappers over Polymarket public APIs (no auth).
Gamma: https://gamma-api.polymarket.com  CLOB: https://clob.polymarket.com
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
import requests

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
S = requests.Session()
S.headers["User-Agent"] = "penny-scanner-demo/0.1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _events(params: dict) -> list[dict]:
    r = S.get(f"{GAMMA}/events", params={"tag_slug": "bitcoin", **params}, timeout=20)
    r.raise_for_status()
    return [e for e in r.json() if "Up or Down" in e.get("title", "")]


def _flatten(events: list[dict]) -> list[dict]:
    out = []
    for e in events:
        for m in e.get("markets", []):
            try:
                outcomes = json.loads(m.get("outcomes") or "[]")
                prices = [float(p) for p in json.loads(m.get("outcomePrices") or "[]")]
                tokens = json.loads(m.get("clobTokenIds") or "[]")
            except (ValueError, TypeError):
                continue
            out.append({
                "title": e["title"], "slug": e.get("slug"), "end": m.get("endDate") or e.get("endDate"),
                "outcomes": outcomes, "prices": prices, "tokens": tokens,
                "volume": float(m.get("volume") or 0), "best_bid": m.get("bestBid"), "best_ask": m.get("bestAsk"),
            })
    return out


def live_markets(limit: int = 100) -> list[dict]:
    return _flatten(_events({"closed": "false", "end_date_min": _now_iso(), "order": "endDate",
                             "ascending": "true", "limit": limit}))


def resolved_markets(limit: int = 40) -> list[dict]:
    return _flatten(_events({"closed": "true", "end_date_max": _now_iso(), "order": "endDate",
                             "ascending": "false", "limit": limit}))


def book(token_id: str) -> dict:
    r = S.get(f"{CLOB}/book", params={"token_id": token_id}, timeout=15)
    r.raise_for_status()
    b = r.json()
    bids = sorted(((float(x["price"]), float(x["size"])) for x in b.get("bids", [])), reverse=True)
    asks = sorted((float(x["price"]), float(x["size"])) for x in b.get("asks", []))
    return {"bids": bids, "asks": asks}


def price_history(token_id: str, before_ts: float | None = None) -> list[float]:
    """1-min prices; only points strictly before `before_ts` (unix) so post-resolution 0/1 ticks are excluded."""
    r = S.get(f"{CLOB}/prices-history", params={"market": token_id, "interval": "1d", "fidelity": 1}, timeout=15)
    r.raise_for_status()
    return [float(p["p"]) for p in r.json().get("history", []) if before_ts is None or p["t"] < before_ts]
