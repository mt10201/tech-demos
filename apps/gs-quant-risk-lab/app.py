"""gs-quant Risk Lab: offline risk and fat-tail analytics for ETFs and strategy sleeves.

Research only. No broker code, no API keys, no orders.
"""
from __future__ import annotations

import datetime as dt
import warnings

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

warnings.filterwarnings("ignore")

from risklab import analytics as an  # noqa: E402
from risklab import data as dm  # noqa: E402
from risklab import tails as tl  # noqa: E402

st.set_page_config(page_title="gs-quant Risk Lab", layout="wide")

DISCLAIMER = ("Research only. Not investment advice. This app has no broker connection, keys or order logic; "
              "it reads public daily prices and CSVs you upload. The bundled sleeve sample is SYNTHETIC.")


@st.cache_data(ttl=3600, show_spinner="Downloading daily prices from yfinance...")
def cached_prices(tickers: tuple[str, ...], start: str) -> pd.DataFrame:
    return dm.download_prices(list(tickers), start=start)


def csv_button(df: pd.DataFrame, name: str, key: str) -> None:
    st.download_button(f"Download {name}.csv", df.to_csv().encode(), file_name=f"{name}.csv", mime="text/csv",
                       key=key)


def ann_label(n: int) -> str:
    return "365 (calendar, 24/7 markets)" if n == 365 else "252 (trading days)"


# ---------------- sidebar ----------------
st.sidebar.title("gs-quant Risk Lab")
preset = st.sidebar.radio("Ticker universe", ["Default (SPY, TLT, GLD)", "Sleeve ETFs preset", "Custom"])
if preset.startswith("Default"):
    tick_text = ", ".join(dm.DEFAULT_TICKERS)
elif preset.startswith("Sleeve"):
    tick_text = ", ".join(dm.SLEEVE_ETF_PRESET)
else:
    tick_text = st.sidebar.text_input("Tickers (comma separated)", "SPY, TLT, GLD, BTC-USD")
tickers = dm.parse_tickers(tick_text)
st.sidebar.caption("Tickers: " + ", ".join(tickers))
start = st.sidebar.date_input("Start date", dt.date.today() - dt.timedelta(days=365 * 10))
drop_today = st.sidebar.checkbox("Drop today's bar if the market may still be open", value=True,
                                 help="Today's daily candle is unfinished until the close.")

st.sidebar.subheader("Strategy sleeves (optional)")
sleeve_mode = st.sidebar.radio("Sleeve returns", ["None", "Bundled SYNTHETIC sample", "Upload CSV"], index=1)
upload = None
if sleeve_mode == "Upload CSV":
    upload = st.sidebar.file_uploader("CSV with columns date,sleeve,return (decimal, 0.01 = +1%)", type="csv")
st.sidebar.download_button("Download sample CSV", dm.SAMPLE_SLEEVES_PATH.read_bytes(),
                           file_name="sample_sleeves.csv", mime="text/csv")

st.sidebar.subheader("Windows (trailing only)")
vol_w = st.sidebar.number_input("Volatility window (days)", 5, 252, 21)
z_w = st.sidebar.number_input("Z-score window (days)", 10, 504, 63)
beta_w = st.sidebar.number_input("Beta window (days)", 20, 504, 63)
corr_w = st.sidebar.number_input("Correlation window (days)", 20, 504, 63)
ann_mode = st.sidebar.selectbox("Annualization", ["Auto per series", "252 for all", "365 for all"],
                                help="Auto: 365 if a series has weekend observations (crypto), else 252.")

st.sidebar.subheader("Tails")
block = st.sidebar.number_input("Bootstrap block length (days)", 1, 60, 10)
n_boot = st.sidebar.select_slider("Bootstrap resamples", [200, 500, 1000, 2000], 1000)
do_stable = st.sidebar.checkbox("Fit Levy-stable alpha (McCulloch quantile method)", value=True)
stress_thr = st.sidebar.slider("Stress day: SPY daily return below", -5.0, -0.5, -2.0, 0.25, format="%.2f%%") / 100

# ---------------- data ----------------
st.title("gs-quant Risk Lab")
st.caption(DISCLAIMER)

all_tickers = tuple(dict.fromkeys(tickers + dm.BENCHMARKS))
try:
    prices = cached_prices(all_tickers, str(start))
except Exception as e:  # network or yfinance failure
    st.error(f"Price download failed: {e}")
    prices = pd.DataFrame()
if drop_today and not prices.empty and prices.index[-1].date() >= dt.date.today():
    prices = prices.iloc[:-1]
missing = [t for t in all_tickers if t not in prices.columns]
if missing:
    st.warning("No data for: " + ", ".join(missing))
rets_all = dm.prices_to_returns(prices) if not prices.empty else pd.DataFrame()
bench = rets_all[[b for b in dm.BENCHMARKS if b in rets_all.columns]]

sleeves = pd.DataFrame()
try:
    if sleeve_mode.startswith("Bundled"):
        sleeves = dm.load_sample_sleeves()
    elif sleeve_mode == "Upload CSV" and upload is not None:
        sleeves = dm.parse_sleeve_csv(upload.getvalue())
except dm.SleeveCSVError as e:
    st.error(f"Sleeve CSV rejected: {e}")
if not sleeves.empty:
    sleeves = sleeves[sleeves.index >= pd.Timestamp(start)]
    sleeves.columns = [f"{c} (sleeve)" for c in sleeves.columns]

returns = pd.concat([rets_all[[t for t in tickers if t in rets_all.columns]], sleeves], axis=1).sort_index()
if returns.empty:
    st.stop()
series = list(returns.columns)
ann = {c: (dm.detect_annualization(returns[c]) if ann_mode.startswith("Auto")
           else (252 if ann_mode.startswith("252") else 365)) for c in series}

c1, c2, c3 = st.columns(3)
c1.metric("Series", len(series))
c2.metric("First date", str(returns.index.min().date()))
c3.metric("Last date", str(returns.index.max().date()))
st.caption("Annualization: " + "; ".join(f"{c}: {ann_label(a)}" for c, a in ann.items()))

tab_roll, tab_tail, tab_corr, tab_data = st.tabs(["Rolling risk", "Fat tails", "Correlation", "Data & method"])

# ---------------- rolling ----------------
with tab_roll:
    st.subheader(f"Trailing {vol_w}-day annualised volatility (gs_quant.volatility)")
    vol = pd.DataFrame({c: an.rolling_vol(returns[c], vol_w, ann[c]) for c in series})
    st.plotly_chart(px.line(vol, labels={"value": "vol %", "index": ""}), width="stretch")
    st.caption("Each value uses only the previous N days, including that day. Percent per year, "
               "annualised with sqrt(252) or sqrt(365) as labelled above.")

    st.subheader("Drawdown from running peak")
    dd = pd.DataFrame({c: an.drawdown_series(returns[c]) for c in series}) * 100
    st.plotly_chart(px.line(dd, labels={"value": "drawdown %", "index": ""}), width="stretch")

    st.subheader(f"Trailing {z_w}-day z-score of price (gs_quant.zscores)")
    z = pd.DataFrame({c: an.rolling_zscore(returns[c], z_w) for c in series})
    fig = px.line(z, labels={"value": "z", "index": ""})
    for y in (-2, 2):
        fig.add_hline(y=y, line_dash="dot", line_color="grey")
    st.plotly_chart(fig, width="stretch")

    st.subheader(f"Trailing {beta_w}-day beta (gs_quant.beta)")
    bsel = st.radio("Benchmark", list(bench.columns), horizontal=True, key="bench")
    rb = pd.DataFrame({c: an.rolling_beta(returns[c], bench[bsel], beta_w) for c in series if c != bsel})
    st.plotly_chart(px.line(rb, labels={"value": f"beta to {bsel}", "index": ""}), width="stretch")

    snap = pd.DataFrame({
        "annualization": {c: ann[c] for c in series},
        f"vol_{vol_w}d_%": vol.ffill().iloc[-1],
        "drawdown_%": dd.ffill().iloc[-1],
        f"zscore_{z_w}d": z.ffill().iloc[-1],
        "gs_max_drawdown_%": {c: an.gs_max_drawdown(returns[c]) * 100 for c in series},
    })
    st.markdown("**Latest values**")
    st.dataframe(snap.style.format(precision=2), width="stretch")
    csv_button(snap, "latest_rolling_snapshot", "dl_snap")

    st.markdown("**Full-sample single-factor betas** (each column is a separate one-factor regression)")
    bt = an.beta_table(returns, bench)
    st.dataframe(bt.style.format(precision=3), width="stretch")
    csv_button(bt, "beta_table", "dl_beta")
    with st.expander("Download rolling series"):
        csv_button(vol, "rolling_vol", "dl_vol")
        csv_button(dd, "drawdowns", "dl_dd")
        csv_button(z, "zscores", "dl_z")
        csv_button(rb, f"rolling_beta_{bsel}", "dl_rb")

# ---------------- tails ----------------
with tab_tail:
    st.subheader("Fat-tail summary (daily simple returns, selected sample)")
    summ = tl.tail_summary(returns, block=int(block), n_boot=int(n_boot))
    pct_cols = [c for c in summ.columns if c.startswith("cvar") or "drawdown" in c and "days" not in c]
    fmt = {c: "{:.2%}" for c in pct_cols}
    fmt.update({c: "{:.2f}" for c in ["excess_kurtosis", "skew", "hill_alpha_left", "hill_alpha_right"]})
    st.dataframe(summ.style.format(fmt), width="stretch")
    st.caption(f"CVaR = average loss on the worst 5% / 1% of days (positive = loss). Bootstrap: moving blocks of "
               f"{block} days, {n_boot} resamples, p05-p95 band. Hill alpha at k = top 5% of days; below 2 means "
               "infinite variance, Gaussian is effectively infinite. Excess kurtosis 0 = Gaussian.")
    csv_button(summ, "tail_summary", "dl_tail")

    st.subheader("Hill tail-index stability across k (left tail = losses)")
    hc = pd.DataFrame({c: tl.hill_curve(returns[c], "left") for c in series})
    fig = px.line(hc, labels={"value": "Hill alpha", "k": "k (number of largest losses used)"})
    fig.add_hline(y=2, line_dash="dash", line_color="red", annotation_text="alpha = 2 (infinite variance)")
    st.plotly_chart(fig, width="stretch")
    st.caption("A flat stretch of the curve is where the estimate is trustworthy. Small k = noisy; large k drifts "
               "into the body of the distribution.")
    csv_button(hc, "hill_curve_left", "dl_hill")

    if do_stable:
        st.subheader("Levy-stable vs Gaussian")
        pick = st.selectbox("Series", series, key="stable_pick")
        r = returns[pick].dropna()
        fit = tl.stable_fit(r)
        if fit:
            st.write(f"Stable alpha **{fit['alpha']:.2f}** (2.0 = Gaussian), beta {fit['beta']:.2f}, "
                     f"scale {fit['scale']:.4f}.")
            tp = tl.tail_prob_table(r, fit)
            st.dataframe(tp.style.format({"empirical": "{:.3%}", "gaussian": "{:.5%}", "stable": "{:.3%}",
                                          "gaussian_expected_days": "{:.3f}"}), width="stretch")
            csv_button(tp, f"tail_probabilities_{pick}", "dl_tp")
            from scipy.stats import levy_stable, norm
            hist, edges = np.histogram(r, bins=120, density=True)
            mids = (edges[1:] + edges[:-1]) / 2
            grid = np.linspace(r.min(), r.max(), 200)
            fig = go.Figure()
            keep = hist > 0
            fig.add_scatter(x=mids[keep], y=hist[keep], mode="markers", name="empirical (histogram)",
                            marker=dict(color="grey", size=6))
            fig.add_scatter(x=grid, y=norm.pdf(grid, r.mean(), r.std()), name="Gaussian")
            fig.add_scatter(x=grid, y=levy_stable.pdf(grid, fit["alpha"], fit["beta"], fit["loc"], fit["scale"]),
                            name=f"stable alpha={fit['alpha']:.2f}")
            lo = np.log10(hist[keep].min()) - 1
            hi = np.log10(hist.max()) + 0.5
            fig.update_yaxes(type="log", title="density (log scale)", range=[lo, hi])
            fig.update_xaxes(title="daily return", tickformat=".0%")
            st.plotly_chart(fig, width="stretch")
            st.caption("Log scale shows the tails: the Gaussian curve drops off far faster than real returns.")

# ---------------- correlation ----------------
with tab_corr:
    st.subheader("Correlation of daily returns (full sample, pairwise common days)")
    cm = an.corr_matrix(returns)
    st.plotly_chart(px.imshow(cm, text_auto=".2f", zmin=-1, zmax=1, color_continuous_scale="RdBu_r",
                              aspect="auto"), width="stretch")
    csv_button(cm, "correlation_full", "dl_cm")

    if "SPY" in bench.columns:
        sc, ndays = an.stress_corr(returns, bench["SPY"], stress_thr)
        st.subheader(f"Stress-only correlation: {ndays} days with SPY below {stress_thr:.2%}")
        st.plotly_chart(px.imshow(sc, text_auto=".2f", zmin=-1, zmax=1, color_continuous_scale="RdBu_r",
                                  aspect="auto"), width="stretch")
        per = returns.reindex(bench["SPY"][bench["SPY"] < stress_thr].index).notna().sum()
        st.caption("Stress days available per series: " + ", ".join(f"{k} {int(v)}" for k, v in per.items()))
        st.caption("Diversification that disappears on stress days is the main thing to look for. "
                   "With few stress days these estimates are noisy (needs at least 5 shared days per pair).")
        csv_button(sc, "correlation_stress", "dl_sc")
        delta = sc - cm
        with st.expander("Stress minus full-sample correlation"):
            st.dataframe(delta.style.format(precision=2),
                         width="stretch")
            csv_button(delta, "correlation_stress_minus_full", "dl_delta")

    st.subheader(f"Trailing {corr_w}-day correlation (gs_quant.correlation)")
    anchor = st.selectbox("Correlate every series against", series, index=series.index("SPY") if "SPY" in series else 0)
    rc = pd.DataFrame({c: an.rolling_corr(returns[c], returns[anchor], corr_w) for c in series if c != anchor})
    st.plotly_chart(px.line(rc, labels={"value": f"corr to {anchor}", "index": ""}), width="stretch")
    csv_button(rc, f"rolling_corr_{anchor}", "dl_rc")

# ---------------- data ----------------
with tab_data:
    st.subheader("Daily returns used")
    st.dataframe(returns.tail(300).style.format("{:.4%}"), width="stretch")
    csv_button(returns, "daily_returns", "dl_ret")
    st.markdown("""
**Method notes**
- Prices: yfinance daily closes adjusted for splits and dividends. Sleeves: your CSV (`date,sleeve,return`).
- Rolling metrics call `gs_quant.timeseries` (`volatility`, `zscores`, `beta`, `correlation`, `max_drawdown`) with
  `Window(N, N)`: trailing N observations, first N partial values dropped. No future data is used.
- Pairwise metrics use only dates both series share (sleeves vs ETFs may have different calendars).
- Tail statistics are descriptive over the whole selected sample, not forecasts.
- `gs-quant` runs fully offline here; no Marquee login. Its pricing and risk-model APIs are not used.
""")
