"""Unit tests for Gaussian HMM market-regime detector and no-lookahead backtest."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pytest

from hmm_demo import (
    build_backtest_equity_and_drawdown_chart,
    build_export_dataframe,
    build_lookahead_comparison_chart,
    build_regime_price_and_prob_chart,
    build_transition_matrix_heatmap,
    compute_features,
    compute_performance_metrics,
    compute_regime_summary_table,
    compute_target_weights_from_proba,
    default_regime_weights,
    fetch_prices,
    fit_gaussian_hmm,
    fit_student_t_hmm,
    forward_filter_proba,
    generate_synthetic_prices,
    normalize_tickers,
    run_walk_forward_backtest,
    sort_hmm_states_by_volatility,
    walk_forward_hmm_inference,
)


def test_feature_computation_is_causal_and_valid():
    """Verify log_return and rolling_vol match manual formulas and use no future rows."""
    prices = generate_synthetic_prices(["SPY", "TLT", "GLD"], n_days=400, seed=7)
    feat = compute_features(prices, primary_ticker="SPY", vol_window=20)

    assert len(feat) == 400 - 20
    assert {"price_SPY", "ret_SPY", "log_return", "rolling_vol"}.issubset(feat.columns)
    assert not feat.isna().any().any()

    expected_log_ret = np.log(prices["SPY"] / prices["SPY"].shift(1)).dropna()
    expected_vol = expected_log_ret.rolling(20).std(ddof=1) * np.sqrt(252.0)
    np.testing.assert_allclose(feat["log_return"].to_numpy(), expected_log_ret.iloc[19:].to_numpy(), rtol=1e-12)
    np.testing.assert_allclose(feat["rolling_vol"].to_numpy(), expected_vol.dropna().to_numpy(), rtol=1e-12)

    # Perturbing future prices after index 250 must not alter features before index 250
    prices_perturbed = prices.copy()
    prices_perturbed.iloc[250:, 0] *= 3.5
    feat_perturbed = compute_features(prices_perturbed, primary_ticker="SPY", vol_window=20)
    cutoff = 250 - 20
    np.testing.assert_array_equal(
        feat.iloc[:cutoff][["log_return", "rolling_vol"]].to_numpy(),
        feat_perturbed.iloc[:cutoff][["log_return", "rolling_vol"]].to_numpy(),
    )


@pytest.mark.parametrize("n_states", [2, 3, 4])
def test_state_sorting_by_volatility_is_deterministic(n_states: int):
    """States must always be ordered strictly from lowest realized vol (0) to highest vol (K-1)."""
    prices = generate_synthetic_prices(["SPY", "TLT", "GLD"], n_days=900, seed=42)
    feat = compute_features(prices, primary_ticker="SPY", vol_window=20)
    X = feat[["log_return", "rolling_vol"]].to_numpy()

    model = fit_gaussian_hmm(X, n_states=n_states, random_state=42)
    state_vols = model.means_[:, 1]
    assert np.all(np.diff(state_vols) >= -1e-12), f"State vols not sorted ascending: {state_vols}"

    # Intentionally scramble state order and verify sort_hmm_states_by_volatility restores exact order
    orig_means = model.means_.copy()
    orig_trans = model.transmat_.copy()
    orig_proba = forward_filter_proba(model, X)

    rev = np.arange(n_states - 1, -1, -1)
    model.startprob_ = model.startprob_[rev]
    model.transmat_ = model.transmat_[np.ix_(rev, rev)]
    model.means_ = model.means_[rev]
    model._covars_ = model._covars_[rev]

    sort_hmm_states_by_volatility(model)
    np.testing.assert_allclose(model.means_, orig_means, atol=1e-12)
    np.testing.assert_allclose(model.transmat_, orig_trans, atol=1e-12)
    np.testing.assert_allclose(forward_filter_proba(model, X), orig_proba, atol=1e-12)


def test_forward_only_filter_has_zero_lookahead_vs_smoother():
    """
    Prove that `forward_filter_proba(model, X)[:t]` is invariant when future observations
    `X[t:]` are replaced by an extreme market crash, whereas `model.predict_proba(X)[:t]`
    (hmmlearn's forward-backward smoother) leaks future crash data backward into `< t`.
    """
    prices = generate_synthetic_prices(["SPY", "TLT", "GLD"], n_days=600, seed=11)
    feat = compute_features(prices, primary_ticker="SPY", vol_window=20)
    X_clean = feat[["log_return", "rolling_vol"]].to_numpy().copy()

    model = fit_gaussian_hmm(X_clean, n_states=3, random_state=42)

    cutoff = 350
    X_shocked = X_clean.copy()
    # Inject a severe future volatility shock from `cutoff` onward
    X_shocked[cutoff:, 0] = -0.06
    X_shocked[cutoff:, 1] = 0.75

    fwd_clean = forward_filter_proba(model, X_clean)
    fwd_shocked = forward_filter_proba(model, X_shocked)

    # 1. Forward-only probabilities sum to 1 and are 100% identical strictly up to `cutoff`
    np.testing.assert_allclose(fwd_clean.sum(axis=1), np.ones(len(X_clean)), atol=1e-12)
    np.testing.assert_allclose(fwd_clean[:cutoff], fwd_shocked[:cutoff], atol=1e-15)

    # 2. By contrast, hmmlearn's standard predict_proba smoother leaks the future shock into t < cutoff
    smooth_clean = model.predict_proba(X_clean)
    smooth_shocked = model.predict_proba(X_shocked)
    pre_cutoff_leak = np.max(np.abs(smooth_clean[cutoff - 10 : cutoff] - smooth_shocked[cutoff - 10 : cutoff]))
    assert pre_cutoff_leak > 1e-3, "Expected smoother predict_proba to leak future shock into prior days"


def test_walk_forward_backtest_strictly_uses_t_minus_1_weights():
    """
    Verify that day t's applied portfolio weight is strictly determined by day t-1's
    regime probabilities, and altering returns/probabilities at >= t never affects
    applied weights on day <= t.
    """
    prices = generate_synthetic_prices(["SPY", "TLT", "GLD"], n_days=500, seed=99)
    feat = compute_features(prices, primary_ticker="SPY", vol_window=20)
    X = feat[["log_return", "rolling_vol"]].to_numpy()
    model = fit_gaussian_hmm(X, n_states=3, random_state=42)
    proba = forward_filter_proba(model, X)
    W = default_regime_weights(3, ["SPY", "TLT", "GLD"]).to_numpy()

    for mode in ("discrete", "prob_weighted"):
        target_w, applied_w = compute_target_weights_from_proba(proba, W, sizing_mode=mode)
        np.testing.assert_allclose(applied_w[1:], target_w[:-1], atol=1e-15)
        np.testing.assert_allclose(applied_w.sum(axis=1), np.ones(len(applied_w)), atol=1e-12)

    bt1 = run_walk_forward_backtest(
        feat,
        causal_proba=proba,
        smoother_proba=proba,
        tickers=["SPY", "TLT", "GLD"],
        sizing_mode="discrete",
        cost_bps=5.0,
    )

    feat_mut = feat.copy()
    proba_mut = proba.copy()
    feat_mut.iloc[300:, feat_mut.columns.get_loc("ret_SPY")] = -0.15
    proba_mut[300:] = np.array([0.0, 0.0, 1.0])

    bt2 = run_walk_forward_backtest(
        feat_mut,
        causal_proba=proba_mut,
        smoother_proba=proba_mut,
        tickers=["SPY", "TLT", "GLD"],
        sizing_mode="discrete",
        cost_bps=5.0,
    )

    np.testing.assert_allclose(
        bt1.curves_df["HMM Walk-Forward (No Look-Ahead)"].iloc[:300].to_numpy(),
        bt2.curves_df["HMM Walk-Forward (No Look-Ahead)"].iloc[:300].to_numpy(),
        atol=1e-15,
    )
    np.testing.assert_allclose(bt1.applied_weights[300], bt2.applied_weights[300], atol=1e-15)


def test_csv_export_and_offline_fallback_schema():
    """Verify bundled offline dataset loading, regime summary table, and bot CSV export columns."""
    prices, src = fetch_prices(["SPY", "TLT", "GLD"], period="5y", allow_network=False)
    assert "offline" in src.lower() or "bundled" in src.lower()
    assert list(prices.columns) == ["SPY", "TLT", "GLD"]

    feat = compute_features(prices, primary_ticker="SPY", vol_window=20)
    X = feat[["log_return", "rolling_vol"]].to_numpy()
    res = walk_forward_hmm_inference(X, n_states=3, min_train_days=252, refit_every=126)

    summary = compute_regime_summary_table(feat, res.walk_forward_states, res.model.transmat_, 3, "SPY")
    assert len(summary) == 3
    assert np.isclose(summary["% of Time"].sum(), 100.0, atol=0.3)

    bt = run_walk_forward_backtest(
        feat,
        causal_proba=res.walk_forward_proba,
        smoother_proba=res.smoother_proba,
        tickers=["SPY", "TLT", "GLD"],
    )
    export_df = build_export_dataframe(feat, res.walk_forward_proba, res.smoother_proba, bt)

    expected_cols = {
        "date",
        "close_SPY",
        "close_TLT",
        "close_GLD",
        "log_return",
        "rolling_vol_ann",
        "causal_regime_id",
        "causal_regime_label",
        "smoother_regime_id",
        "smoother_regime_label",
        "prob_state_0_bull_calm",
        "prob_state_1_neutral_transition",
        "prob_state_2_bear_high_vol",
        "target_weight_SPY",
        "target_weight_TLT",
        "target_weight_GLD",
        "applied_weight_SPY",
        "applied_weight_TLT",
        "applied_weight_GLD",
        "strategy_daily_return",
        "strategy_equity",
        "buy_hold_SPY_equity",
    }
    assert expected_cols.issubset(export_df.columns)
    assert len(export_df) == len(feat)
    prob_sum = (
        export_df["prob_state_0_bull_calm"]
        + export_df["prob_state_1_neutral_transition"]
        + export_df["prob_state_2_bear_high_vol"]
    )
    np.testing.assert_allclose(prob_sum.to_numpy(), np.ones(len(export_df)), atol=1e-4)


def test_charts_and_helpers_build_cleanly():
    """Verify ticker normalization, performance metrics, and all Plotly chart builders."""
    assert normalize_tickers("spy", ["tlt", "gld", "SPY"]) == ["SPY", "TLT", "GLD"]
    m = compute_performance_metrics(np.array([0.01, -0.005, 0.008, 0.002]), np.array([0.0, 0.5, 0.0, 0.0]), "Test")
    assert m["Total Return (%)"] > 0.0
    assert m["Max Drawdown (%)"] <= 0.0

    prices = generate_synthetic_prices(["SPY", "TLT", "GLD"], n_days=350, seed=5)
    feat = compute_features(prices, primary_ticker="SPY", vol_window=20)
    X = feat[["log_return", "rolling_vol"]].to_numpy()
    res = walk_forward_hmm_inference(X, n_states=3, min_train_days=150, refit_every=100)
    bt = run_walk_forward_backtest(feat, res.walk_forward_proba, res.smoother_proba, ["SPY", "TLT", "GLD"])

    fig1 = build_regime_price_and_prob_chart(feat, res.walk_forward_proba, res.walk_forward_states, "SPY", 3)
    fig2 = build_transition_matrix_heatmap(res.model.transmat_, 3)
    fig3 = build_lookahead_comparison_chart(feat.index, res.forward_only_proba, res.smoother_proba, 3)
    fig4 = build_backtest_equity_and_drawdown_chart(bt)

    assert len(fig1.data) >= 5
    assert len(fig2.data) == 1
    assert len(fig3.data) == 3
    assert len(fig4.data) >= 8


def test_student_t_hmm_fat_tail_robustness():
    """
    Verify StudentTHMM fits cleanly, sorts states by ascending volatility, preserves
    zero look-ahead in forward_filter_proba, and resists single-day fat-tailed return
    spikes during a calm regime better than GaussianHMM.
    """
    prices = generate_synthetic_prices(["SPY", "TLT", "GLD"], n_days=600, seed=42)
    feat = compute_features(prices, primary_ticker="SPY", vol_window=20)
    X = feat[["log_return", "rolling_vol"]].to_numpy().copy()

    g_model = fit_gaussian_hmm(X, n_states=3, random_state=42)
    t_model = fit_student_t_hmm(X, n_states=3, df_nu=5.0, estimate_nu=True, random_state=42)

    assert np.all(np.diff(t_model.means_[:, 1]) >= -1e-12)
    t_proba = forward_filter_proba(t_model, X)
    np.testing.assert_allclose(t_proba.sum(axis=1), np.ones(len(X)), atol=1e-12)

    # Inject a single-day -4.5% return shock on a calm bull day while rolling_vol remains calm
    calm_indices = np.where((np.argmax(t_proba, axis=1) == 0) & (np.argmax(forward_filter_proba(g_model, X), axis=1) == 0))[0]
    calm_idx = int(calm_indices[len(calm_indices) // 2])
    X_spike = X.copy()
    X_spike[calm_idx, 0] = -0.045  # single-day -4.5% outlier candle, rolling_vol unchanged

    g_prob_spike = forward_filter_proba(g_model, X_spike)[calm_idx, 0]
    t_prob_spike = forward_filter_proba(t_model, X_spike)[calm_idx, 0]

    # Student-t emission retains higher probability of staying in the calm regime on an isolated 1-day spike
    assert t_prob_spike > g_prob_spike

    res_t = walk_forward_hmm_inference(
        X, n_states=3, min_train_days=252, refit_every=126, distribution="student_t", df_nu=5.0
    )
    assert res_t.walk_forward_proba.shape == (len(X), 3)


def test_switching_stats_counts_switches_and_whipsaws():
    """A 1-day blip and a 2-day blip are whipsaws; a long spell is not; edge spells are excluded."""
    from hmm_demo import compute_switching_stats

    states = np.array([0] * 100 + [1] + [0] * 100 + [2, 2] + [0] * 100 + [1] * 50)
    stats = compute_switching_stats(states)
    assert stats["switches"] == 5.0
    assert stats["whipsaws"] == 2.0
    years = len(states) / 252.0
    assert stats["switches_per_year"] == pytest.approx(5.0 / years)
    assert compute_switching_stats(np.zeros(10, dtype=int))["switches"] == 0.0
    # start offset drops the early blip
    assert compute_switching_stats(states, start=150)["whipsaws"] == 1.0
