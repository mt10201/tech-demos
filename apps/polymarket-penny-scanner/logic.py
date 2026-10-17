"""Pure logic: payoff math, threshold filter, history aggregation."""
from __future__ import annotations


def payoff(stake: float, price: float, payout_per_share: float = 1.0) -> dict:
    """Buying at `price` (0-1) per share; each winning share pays `payout_per_share`."""
    if not 0 < price < 1:
        raise ValueError("price must be between 0 and 1 (exclusive)")
    if stake < 0:
        raise ValueError("stake must be >= 0")
    shares = stake / price
    payout = shares * payout_per_share
    return {"shares": shares, "payout_if_win": payout, "profit_if_win": payout - stake,
            "loss_if_lose": -stake, "breakeven_win_rate": price / payout_per_share}


def penny_sides(markets: list[dict], threshold: float) -> list[dict]:
    """Return one row per side priced <= threshold (0 < price). Uses best price given per side."""
    rows = []
    for m in markets:
        for i, (name, price) in enumerate(zip(m["outcomes"], m["prices"])):
            if 0 < price <= threshold:
                rows.append({**m, "side": name, "side_price": price,
                             "token": m["tokens"][i] if i < len(m["tokens"]) else None})
    return rows


def history_summary(records: list[dict]) -> dict:
    """records: {'touched': bool, 'won': bool} per (market, side)."""
    touched = [r for r in records if r["touched"]]
    wins = sum(r["won"] for r in touched)
    return {"sides_checked": len(records), "touched": len(touched), "won": wins,
            "hit_rate": wins / len(touched) if touched else None}
