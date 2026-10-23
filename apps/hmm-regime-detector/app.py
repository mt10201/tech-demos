"""Streamlit app: Gaussian Hidden Markov Model (hmmlearn) Market-Regime Detector & Walk-Forward Backtest."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from hmm_demo import (
    HISTORY_WINDOWS,
    build_backtest_equity_and_drawdown_chart,
    build_export_dataframe,
    build_lookahead_comparison_chart,
    build_regime_price_and_prob_chart,
    build_transition_matrix_heatmap,
    compute_features,
    compute_regime_summary_table,
    default_regime_weights,
    fetch_prices,
    get_regime_metadata,
    normalize_tickers,
    run_walk_forward_backtest,
    walk_forward_hmm_inference,
)

st.set_page_config(
    page_title="HMM Market-Regime Detector (hmmlearn)",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=600, show_spinner=False)
def _cached_fetch_prices(
    tickers: tuple[str, ...],
    period: str,
    allow_network: bool,
) -> tuple[pd.DataFrame, str]:
    return fetch_prices(tickers=tickers, period=period, allow_network=allow_network)


@st.cache_data(show_spinner=False)
def _cached_run_hmm(
    prices_df: pd.DataFrame,
    primary_ticker: str,
    vol_window: int,
    n_states: int,
    min_train_days: int,
    refit_every: int,
    covariance_type: str,
):
    feat = compute_features(prices_df, primary_ticker=primary_ticker, vol_window=vol_window)
    X = feat[["log_return", "rolling_vol"]].to_numpy()
    hmm_res = walk_forward_hmm_inference(
        X,
        n_states=n_states,
        min_train_days=min_train_days,
        refit_every=refit_every,
        covariance_type=covariance_type,
        random_state=42,
    )
    return feat, hmm_res


def _get_query_param(name: str, default: str) -> str:
    val = st.query_params.get(name, default)
    if isinstance(val, list):
        return str(val[0]) if val else default
    return str(val)


def main() -> None:
    qp_view = _get_query_param("view", "all").lower()
    qp_states = int(_get_query_param("states", "3")) if _get_query_param("states", "3").isdigit() else 3
    qp_states = qp_states if qp_states in (2, 3, 4) else 3
    qp_period = _get_query_param("period", "10y").lower()
    if qp_period not in HISTORY_WINDOWS:
        qp_period = "10y"

    st.title("📈 Gaussian HMM Market-Regime Detector (`hmmlearn`)")
    st.caption(
        "⚠️ **Research & visualization only — not financial advice.** "
        "This tool connects to no brokerage and places no live orders. "
        "Regime probabilities are filtered causally (`alpha` pass + expanding walk-forward refits) "
        "to avoid the future-data leakage inherent in `hmmlearn`'s default `predict` / `predict_proba` smoother."
    )

    with st.sidebar:
        st.header("1. Assets & History")
        primary_ticker = st.text_input("Primary Risk Asset", value="SPY").strip().upper() or "SPY"
        defensive_raw = st.text_input("Defensive / Hedge Assets (comma-separated)", value="TLT, GLD")
        defensive_list = [s.strip().upper() for s in defensive_raw.split(",") if s.strip()]
        if not defensive_list:
            defensive_list = ["TLT", "GLD"]

        period = st.selectbox(
            "History Window",
            options=list(HISTORY_WINDOWS),
            index=list(HISTORY_WINDOWS).index(qp_period),
        )
        data_mode = st.radio(
            "Data Source",
            options=["Live Yahoo Finance (with offline fallback)", "Bundled / Offline Snapshot"],
            index=0,
        )
        allow_network = data_mode.startswith("Live")

        st.divider()
        st.header("2. Gaussian HMM Settings")
        n_states = st.slider(
            "Number of Regimes (K)",
            min_value=2,
            max_value=4,
            value=qp_states,
            help="States are sorted deterministically by ascending realized volatility (State 0 = Calm / Bull, State K-1 = High-Vol / Bear).",
        )
        vol_window = st.slider(
            "Rolling Realized Vol Window (trading days)",
            min_value=10,
            max_value=63,
            value=20,
            step=5,
        )
        covariance_type = st.selectbox(
            "Emission Covariance Type",
            options=["full", "diag"],
            index=0,
        )

        st.divider()
        st.header("3. Look-Ahead Prevention")
        prob_mode = st.selectbox(
            "Active Regime Probability Signal",
            options=[
                "Walk-Forward Expanding + Forward Filter (Strict OOS)",
                "Full-Fit + Causal Forward Filter (Alpha Pass)",
                "Biased Full-Sample Smoother (predict_proba Leak)",
            ],
            index=0,
            help="Controls which probability series shades the price chart and drives the primary strategy.",
        )
        min_train_days = st.slider(
            "Initial Walk-Forward Warmup (days)",
            min_value=252,
            max_value=1008,
            value=504,
            step=63,
        )
        refit_every = st.slider(
            "Walk-Forward Refit Cadence (days)",
            min_value=21,
            max_value=126,
            value=63,
            step=21,
        )

        st.divider()
        st.header("4. Walk-Forward Backtest")
        sizing_mode_label = st.radio(
            "Position Sizing Mode (at t-1 for day t)",
            options=["Discrete Regime State (Argmax)", "Probability-Blended Weights"],
            index=0,
        )
        sizing_mode = "discrete" if sizing_mode_label.startswith("Discrete") else "prob_weighted"
        cost_bps = st.number_input(
            "Transaction Cost (bps per one-way turnover)",
            min_value=0.0,
            max_value=50.0,
            value=5.0,
            step=1.0,
        )
        show_smoother_leak = st.checkbox(
            "Overlay Biased Smoother Curve (`predict_proba` leak)",
            value=True,
        )

    tickers = normalize_tickers(primary_ticker, defensive_list)
    prices_df, source_label = _cached_fetch_prices(tuple(tickers), period, allow_network)
    features_df, hmm_res = _cached_run_hmm(
        prices_df,
        primary_ticker=tickers[0],
        vol_window=vol_window,
        n_states=n_states,
        min_train_days=min_train_days,
        refit_every=refit_every,
        covariance_type=covariance_type,
    )

    if prob_mode.startswith("Walk-Forward"):
        active_proba = hmm_res.walk_forward_proba
        active_states = hmm_res.walk_forward_states
        mode_short = "Walk-Forward Expanding + Causal Alpha Filter"
    elif prob_mode.startswith("Full-Fit"):
        active_proba = hmm_res.forward_only_proba
        active_states = hmm_res.forward_only_states
        mode_short = "Full-Fit Params + Causal Forward Alpha Filter"
    else:
        active_proba = hmm_res.smoother_proba
        active_states = hmm_res.smoother_states
        mode_short = "Biased Full-Sample Smoother (predict_proba Look-Ahead)"

    with st.sidebar:
        st.subheader("Per-Regime Target Weights")
        st.caption("Rows are sorted by volatility (State 0 = Calmest, State K-1 = Highest Vol).")
        default_w_df = default_regime_weights(n_states=n_states, tickers=tickers)
        edited_w_df = st.data_editor(
            default_w_df,
            use_container_width=True,
            num_rows="fixed",
            key=f"weights_editor_{n_states}_{'_'.join(tickers)}",
        )

    bt_res = run_walk_forward_backtest(
        features_df=features_df,
        causal_proba=active_proba,
        smoother_proba=hmm_res.smoother_proba,
        tickers=tickers,
        regime_weights=edited_w_df,
        sizing_mode=sizing_mode,
        cost_bps=cost_bps,
        forward_only_proba=hmm_res.forward_only_proba,
    )

    export_df = build_export_dataframe(
        features_df=features_df,
        causal_proba=active_proba,
        smoother_proba=hmm_res.smoother_proba,
        backtest_res=bt_res,
    )

    # Top KPI status bar
    meta = get_regime_metadata(n_states)
    latest_date = features_df.index[-1].strftime("%Y-%m-%d")
    latest_state = int(active_states[-1])
    latest_regime_name = meta[latest_state]["name"]
    latest_prob = float(active_proba[-1, latest_state] * 100.0)
    latest_vol = float(features_df["rolling_vol"].iloc[-1] * 100.0)
    latest_weights = bt_res.target_weights[-1]
    weights_str = " / ".join(f"{sym} {w * 100:.0f}%" for sym, w in zip(tickers, latest_weights))

    wf_row = bt_res.metrics_df.iloc[0]
    bh_row = bt_res.metrics_df.iloc[2]
    sm_row = bt_res.metrics_df.iloc[4]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(
        f"Current Regime ({latest_date})",
        f"S{latest_state}: {latest_regime_name}",
        f"{latest_prob:.1f}%filtered prob",
    )
    c2.metric(
        f"{tickers[0]} {vol_window}d Realized Vol",
        f"{latest_vol:.1f}%",
        f"Data: {source_label.split('(')[0].strip()}",
    )
    c3.metric(
        "Walk-Forward Sharpe (No Look-Ahead)",
        f"{wf_row['Sharpe']:.2f}",
        f"{wf_row['CAGR (%)']:.2f}% CAGR | {wf_row['Max Drawdown (%)']:.1f}% MaxDD",
    )
    c4.metric(
        f"Buy & Hold {tickers[0]} Sharpe",
        f"{bh_row['Sharpe']:.2f}",
        f"{bh_row['CAGR (%)']:.2f}% CAGR | {bh_row['Max Drawdown (%)']:.1f}% MaxDD",
    )
    c5.metric(
        "Look-Ahead Smoother Inflation",
        f"{sm_row['Sharpe']:.2f} Sharpe",
        f"{int(hmm_res.lookahead_stats['flip_days_fwd_vs_smoother'])} days flipped by smoother",
        delta_color="inverse",
    )

    st.info(
        f"**Next-Day Target Allocation (signal at close of {latest_date}):** `{weights_str}`  |  "
        f"**Sample Window:** `{features_df.index[0].strftime('%Y-%m-%d')}` to `{latest_date}` "
        f"(`{len(features_df):,}` trading days, `{source_label}`)."
    )

    view_options = {
        "all": "All Sections",
        "regimes": "1. Regime Price & Probabilities",
        "backtest": "2. Walk-Forward Backtest & CSV Export",
        "transitions": "3. Transition Matrix, Stats & Look-Ahead Audit",
    }
    default_view_idx = list(view_options.keys()).index(qp_view) if qp_view in view_options else 0
    selected_view_label = st.radio(
        "View Section",
        options=list(view_options.values()),
        index=default_view_idx,
        horizontal=True,
        label_visibility="collapsed",
    )
    active_view = [k for k, v in view_options.items() if v == selected_view_label][0]

    min_train_dt = (
        features_df.index[hmm_res.min_train_days]
        if hmm_res.min_train_days < len(features_df.index)
        else None
    )

    if active_view in ("all", "regimes"):
        st.subheader(f"1. {tickers[0]} Price Shaded by Regime & Causal Regime Probabilities")
        fig_price = build_regime_price_and_prob_chart(
            features_df=features_df,
            proba=active_proba,
            states=active_states,
            primary_ticker=tickers[0],
            n_states=n_states,
            mode_label=mode_short,
            min_train_date=min_train_dt if prob_mode.startswith("Walk-Forward") else None,
        )
        st.plotly_chart(fig_price, use_container_width=True)

    if active_view in ("all", "backtest"):
        st.subheader("2. Walk-Forward Regime-Switching Backtest (t-1 Signal → t Return)")
        fig_bt = build_backtest_equity_and_drawdown_chart(
            bt=bt_res,
            show_smoother_leak=show_smoother_leak,
        )
        st.plotly_chart(fig_bt, use_container_width=True)

        col_m, col_dl = st.columns([3, 1])
        with col_m:
            st.markdown("**Strategy & Benchmark Performance Summary**")
            st.dataframe(bt_res.metrics_df, use_container_width=True, hide_index=True)
        with col_dl:
            st.markdown("**Bot Signal Export (`CSV`)**")
            st.caption(
                "Exports daily prices, `log_return`, `rolling_vol_ann`, causal regime state, "
                "forward-filtered state probabilities, and next-day target weights for "
                "`@Portfolio Oversight` and `@Strategy Research`."
            )
            csv_bytes = export_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="⬇️ Download Daily Regime & Weights CSV",
                data=csv_bytes,
                file_name=f"hmm_regimes_{'_'.join(tickers)}_{n_states}states.csv",
                mime="text/csv",
                use_container_width=True,
            )

    if active_view in ("all", "transitions"):
        st.subheader("3. Transition Matrix, Per-Regime Summary & Look-Ahead Bias Audit")
        col_hm, col_tbl = st.columns([1.05, 1.45])
        with col_hm:
            fig_hm = build_transition_matrix_heatmap(
                transmat=hmm_res.model.transmat_,
                n_states=n_states,
            )
            st.plotly_chart(fig_hm, use_container_width=True)
        with col_tbl:
            st.markdown(f"**Per-Regime Summary Statistics ({mode_short})**")
            summary_df = compute_regime_summary_table(
                features_df=features_df,
                states=active_states,
                transmat=hmm_res.model.transmat_,
                n_states=n_states,
                primary_ticker=tickers[0],
            )
            st.dataframe(summary_df, use_container_width=True, hide_index=True)
            st.caption(
                f"**Why Look-Ahead Prevention Matters:** `hmmlearn`'s standard `predict_proba(X)` "
                f"runs the forward-backward Baum-Welch smoother $P(S_t \\mid X_{{1:T}})$, which uses future "
                f"returns and volatility spikes to retroactively reclassify `{int(hmm_res.lookahead_stats['flip_days_fwd_vs_smoother'])}` "
                f"days (`{hmm_res.lookahead_stats['disagree_fwd_vs_smoother_pct']:.1f}%` of sample vs. causal forward filter, and "
                f"`{hmm_res.lookahead_stats['disagree_wf_vs_smoother_pct']:.1f}%` vs. expanding walk-forward OOS). "
                f"In our walk-forward backtest, allocation on day $t$ uses only the filtered state at $t-1$."
            )

        fig_la = build_lookahead_comparison_chart(
            dates=features_df.index,
            causal_proba=hmm_res.forward_only_proba,
            smoother_proba=hmm_res.smoother_proba,
            n_states=n_states,
            window_days=504,
        )
        st.plotly_chart(fig_la, use_container_width=True)


if __name__ == "__main__":
    main()
