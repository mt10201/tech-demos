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


scan, calc, hist, bt = st.tabs(["Scanner", "Payoff calculator", "Resolved history", "Backtest"])

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

with bt:
    import json
    from pathlib import Path
    data = Path(__file__).parent / "data"
    f = data / "backtest_results.json"
    if not f.exists():
        st.warning("No backtest yet. Run `python backtest.py --days 30` first.")
    else:
        r = json.loads(f.read_text())
        st.subheader("Backtest: buy any side once it trades at ≤ threshold, hold to resolution")
        b = st.columns(4)
        b[0].metric("Resolved markets", f"{r['markets']:,}")
        b[1].metric("Window", f"{r['range'][0][:10]} → {r['range'][1][:10]}")
        b[2].metric("Price-history gaps (sides)", r["history_gaps_sides"])
        b[3].metric("Excluded before close", f"{r['close_buffer_s']}s")
        st.caption("Markets by duration: " + ", ".join(f"{k}: {v:,}" for k, v in r["markets_by_duration"].items())
                   + f". Price fidelity: {r['price_history_fidelity']} (CLOB prices-history).")
        dur_pick = st.multiselect("Durations", ["all", "5m", "15m", "1h", "4h", "daily/other"], ["all", "5m", "15m", "1h", "4h"])

        def table(rows):
            df = pd.DataFrame(rows)
            df = df[df["duration"].isin(dur_pick)]
            return pd.DataFrame({
                "Threshold": df["threshold_c"].astype(str) + "¢", "Duration": df["duration"], "Sides touched": df["sides"],
                "Wins": df["wins"], "Win rate": (df["win_rate"] * 100).round(2).astype(str) + "%",
                "95% CI (Wilson)": [f"{lo*100:.2f}–{hi*100:.2f}%" for lo, hi in zip(df["ci_low"], df["ci_high"])],
                "Avg entry": df["avg_entry_c"].round(2).astype(str) + "¢",
                "Break-even": (df["breakeven"] * 100).round(2).astype(str) + "%",
                "EV per $1": df["ev_per_$1"].round(3)})

        st.markdown("**Touch model** — entry assumed at exactly the threshold whenever the 1-minute price dipped to it.")
        t = table(r["touch"]); st.dataframe(t, width="stretch", hide_index=True)
        allrows = pd.DataFrame([x for x in r["touch"] if x["duration"] == "all"])
        chart = pd.DataFrame({"threshold": allrows["threshold_c"].astype(str) + "¢",
                              "win rate %": allrows["win_rate"] * 100, "break-even %": allrows["breakeven"] * 100}).set_index("threshold")
        st.bar_chart(chart, stack=False, height=260)
        if r["realistic"]:
            m = r["realistic_meta"]
            st.markdown(f"**Realistic-fill model** — only sides with an actual taker trade at ≤ threshold (data-api /trades), "
                        f"entry at that first trade's price. Sample: {m['sampled_markets']:,} markets; "
                        f"{m['touch_rows_without_fill']:,} of {m['touch_rows_in_sample']:,} touches had no qualifying trade; "
                        f"median shares printed at ≤ threshold: {m['median_fill_shares']:,.0f}.")
            st.dataframe(table(r["realistic"]), width="stretch", hide_index=True)
        wf = data / "wallet_check.json"
        if wf.exists():
            w = json.loads(wf.read_text()); lb = w["leaderboard_all_time"] or {}
            st.subheader("Reality check: the @PolyDekos wallet (0x50f7)")
            c = st.columns(4)
            c[0].metric("All-time PnL (leaderboard)", f"${lb.get('pnl', 0):,.0f}")
            c[1].metric("All-time volume", f"${lb.get('vol', 0):,.0f}")
            c[2].metric(f"BTC Up/Down PnL ({w['range'][0]}→{w['range'][1]})", f"${w['btc_updown_pnl_$']:,}")
            c[3].metric("Closed positions sampled", f"{w['closed_positions_fetched']:,}")
            st.dataframe(pd.DataFrame(w["buckets"]).rename(columns={"entry_bucket_c": "Avg entry (¢)"}), width="stretch", hide_index=True)
            st.caption("Source: data-api /v1/leaderboard and /closed-positions for proxy wallet " + w["wallet"] +
                       ". Closed positions may under-count unredeemed losers.")
