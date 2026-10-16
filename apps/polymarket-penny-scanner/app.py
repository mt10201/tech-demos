"""Polymarket penny-side scanner — read-only Streamlit demo. No wallet, no trading."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
import polyapi
from logic import payoff, penny_sides, history_summary

st.set_page_config(page_title="Polymarket Penny Scanner", layout="wide")
st.title("🪙 Polymarket penny-side scanner")
st.caption("Read-only view of Bitcoin Up or Down markets via Polymarket's public Gamma + CLOB APIs. "
           "No wallet, no keys, no trading. Not financial advice.")

threshold_c = st.sidebar.number_input("Penny threshold (¢)", 0.1, 50.0, 2.0, 0.5)
threshold = threshold_c / 100
if st.sidebar.button("🔄 Refresh"):
    st.cache_data.clear()


@st.cache_data(ttl=20)
def load_live():
    return polyapi.live_markets()


def time_left(end: str) -> str:
    secs = int((datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.now(timezone.utc)).total_seconds())
    if secs <= 0:
        return "closing"
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


scan, calc, hist = st.tabs(["Scanner", "Payoff calculator", "Resolved history"])

with scan:
    markets = load_live()
    rows = [{"Market": m["title"], "Time left": time_left(m["end"]),
             **{f"{o} ¢": round(p * 100, 2) for o, p in zip(m["outcomes"], m["prices"])},
             "Volume $": round(m["volume"]), "Penny?": "🚩" if any(0 < p <= threshold for p in m["prices"]) else ""}
            for m in markets]
    flagged = penny_sides(markets, threshold)
    c1, c2, c3 = st.columns(3)
    c1.metric("Live Up/Down markets", len(markets))
    c2.metric(f"Sides ≤ {threshold_c:g}¢", len(flagged))
    c3.metric("Next close", time_left(markets[0]["end"]) if markets else "—")
    st.subheader("Live markets")
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=320)

    st.subheader("Order-book depth")
    choices = {f"🚩 {r['title']} — {r['side']} @ {r['side_price']*100:.2f}¢": (r, r["side"]) for r in flagged}
    for m in markets[:30]:
        for o in m["outcomes"]:
            choices.setdefault(f"{m['title']} — {o}", (m, o))
    if choices:
        label = st.selectbox("Market side", list(choices))
        m, side = choices[label]
        tok = m["tokens"][m["outcomes"].index(side)]
        b = polyapi.book(tok)
        notional = sum(p * s for p, s in b["asks"] if p <= threshold)
        d1, d2, d3 = st.columns(3)
        d1.metric("Best ask", f"{b['asks'][0][0]*100:.1f}¢" if b["asks"] else "—")
        d2.metric("Best bid", f"{b['bids'][0][0]*100:.1f}¢" if b["bids"] else "—")
        d3.metric(f"Ask $ at ≤ {threshold_c:g}¢", f"${notional:,.2f}")
        l, r = st.columns(2)
        l.write("**Bids**"); l.dataframe(pd.DataFrame(b["bids"][:10], columns=["Price", "Shares"]), hide_index=True)
        r.write("**Asks**"); r.dataframe(pd.DataFrame(b["asks"][:10], columns=["Price", "Shares"]), hide_index=True)

with calc:
    a, b_ = st.columns(2)
    stake = a.number_input("Stake ($)", 0.0, 1e6, 10.0, 1.0)
    price_c = b_.number_input("Buy price (¢)", 0.1, 99.9, threshold_c, 0.1)
    p = payoff(stake, price_c / 100)
    k = st.columns(4)
    k[0].metric("Shares", f"{p['shares']:,.1f}")
    k[1].metric("Payout if wins", f"${p['payout_if_win']:,.2f}")
    k[2].metric("Profit if wins", f"${p['profit_if_win']:,.2f}")
    k[3].metric("Loss if loses", f"${p['loss_if_lose']:,.2f}")
    st.info(f"You need this side to win more than **{p['breakeven_win_rate']:.1%}** of the time to break even "
            "(before fees/slippage). Compare with the Resolved history tab.")

with hist:
    n = st.slider("Recent resolved markets to check", 10, 100, 40, 10)

    @st.cache_data(ttl=300)
    def load_hist(n: int, thr: float):
        res = polyapi.resolved_markets(n)
        jobs = [(m, i) for m in res for i in range(len(m["tokens"]))]
        with ThreadPoolExecutor(8) as ex:
            hists = list(ex.map(lambda j: polyapi.price_history(j[0]["tokens"][j[1]], datetime.fromisoformat(j[0]["end"].replace("Z", "+00:00")).timestamp() - 15), jobs))
        recs = []
        for (m, i), h in zip(jobs, hists):
            low = min(h) if h else None
            recs.append({"Market": m["title"], "Side": m["outcomes"][i],
                         "Low ¢": None if low is None else round(low * 100, 2),
                         "touched": low is not None and 0 < low <= thr, "won": m["prices"][i] >= 0.99})
        return recs

    with st.spinner("Fetching price histories from CLOB…"):
        recs = load_hist(n, threshold)
    s = history_summary(recs)
    h = st.columns(3)
    h[0].metric("Sides checked", s["sides_checked"])
    h[1].metric(f"Traded ≤ {threshold_c:g}¢", s["touched"])
    h[2].metric("…and then won", f"{s['won']} ({s['hit_rate']:.1%})" if s["hit_rate"] is not None else "—")
    st.caption("A side 'touched' the threshold if its 1-minute price history dipped to it before the market closed (post-resolution ticks excluded). "
               "Real fills at that price were not guaranteed.")
    df = pd.DataFrame(recs)
    df["Won"] = df.pop("won").map({True: "✅", False: "❌"})
    df["Touched"] = df.pop("touched").map({True: "🚩", False: ""})
    st.dataframe(df, width="stretch", hide_index=True)
