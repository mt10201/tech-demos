"""Walk-forward regime-switching backtest (strictly t-1 signal -> t return) and CSV export."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from .model import get_regime_metadata


def default_regime_weights(
    n_states: int = 3,
    tickers: Sequence[str] = ("SPY", "TLT", "GLD"),
) -> pd.DataFrame:
    """
    Return default per-regime portfolio target weights (rows = states 0..K-1 sorted
    from lowest vol to highest vol, columns = tickers).
    For the default 3-state (SPY, TLT, GLD) setup:
      - State 0 (Bull / Calm):          100% SPY,  0% TLT,  0% GLD
      - State 1 (Neutral / Transition):  50% SPY, 25% TLT, 25% GLD
      - State 2 (Bear / High-Vol):        0% SPY, 50% TLT, 50% GLD
    """
    symbols = [str(t).strip().upper() for t in tickers if str(t).strip()]
    n_assets = len(symbols)
    meta = get_regime_metadata(n_states)

    if n_states == 2:
        presets = [
            [1.0, 0.0, 0.0],
            [0.0, 0.5, 0.5],
        ]
    elif n_states == 3:
        presets = [
            [1.0, 0.0, 0.0],
            [0.5, 0.25, 0.25],
            [0.0, 0.5, 0.5],
        ]
    elif n_states == 4:
        presets = [
            [1.0, 0.0, 0.0],
            [0.75, 0.15, 0.10],
            [0.35, 0.35, 0.30],
            [0.0, 0.50, 0.50],
        ]
    else:
        raise ValueError(f"Unsupported n_states={n_states}; choose 2, 3, or 4.")

    mat = np.zeros((n_states, n_assets), dtype=float)
    for k, row in enumerate(presets):
        if n_assets == 1:
            mat[k, 0] = row[0]
        elif n_assets == 2:
            mat[k, 0] = row[0]
            mat[k, 1] = row[1] + row[2]
        else:
            mat[k, 0] = row[0]
            mat[k, 1] = row[1]
            rem = row[2]
            for j in range(2, n_assets):
                mat[k, j] = rem / (n_assets - 2)

    df = pd.DataFrame(
        mat,
        index=[f"State {k}: {meta[k]['name']}" for k in range(n_states)],
        columns=symbols,
    )
    return df


def compute_target_weights_from_proba(
    proba: np.ndarray,
    regime_weight_matrix: np.ndarray,
    sizing_mode: str = "discrete",
) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert daily state probabilities `proba` (T, K) and `regime_weight_matrix` (K, M)
    into daily end-of-day target weights `target_weights` (T, M) and `applied_weights` (T, M),
    where `applied_weights[t] = target_weights[t - 1]` (strictly 1-day lagged so day t's
    return is earned using only information available at the close of day t - 1).
    """
    proba_arr = np.asarray(proba, dtype=float)
    W = np.asarray(regime_weight_matrix, dtype=float)
    if proba_arr.ndim != 2 or W.ndim != 2 or proba_arr.shape[1] != W.shape[0]:
        raise ValueError("Shape mismatch between proba (T, K) and regime_weight_matrix (K, M).")

    if sizing_mode == "prob_weighted":
        target_weights = proba_arr @ W
    elif sizing_mode == "discrete":
        active_states = np.argmax(proba_arr, axis=1)
        target_weights = W[active_states]
    else:
        raise ValueError(f"Unknown sizing_mode='{sizing_mode}'. Use 'discrete' or 'prob_weighted'.")

    applied_weights = np.zeros_like(target_weights)
    if len(target_weights) > 0:
        # On the very first bar t=0, start in State 0 (risk-on default) before any signal
        applied_weights[0] = W[0]
        if len(target_weights) > 1:
            applied_weights[1:] = target_weights[:-1]

    return target_weights, applied_weights


def _simulate_portfolio(
    asset_returns: np.ndarray,
    applied_weights: np.ndarray,
    cost_bps: float = 5.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute daily net returns, equity curve (starting at 1.0), underwater drawdown (%),
    and daily one-way turnover given `asset_returns` (T, M) and `applied_weights` (T, M).
    """
    R = np.asarray(asset_returns, dtype=float)
    W = np.asarray(applied_weights, dtype=float)

    # One-way turnover at rebalance before day t opens: 0.5 * sum_j |w_{t,j} - w_{t-1,j}|
    weight_changes = np.zeros_like(W)
    if len(W) > 1:
        weight_changes[1:] = np.abs(W[1:] - W[:-1])
    one_way_turnover = 0.5 * np.sum(weight_changes, axis=1)

    cost_rate = float(cost_bps) / 10_000.0
    gross_ret = np.sum(W * R, axis=1)
    net_ret = gross_ret - one_way_turnover * cost_rate

    equity = np.cumprod(1.0 + net_ret)
    running_peak = np.maximum.accumulate(equity)
    drawdown_pct = (equity / running_peak - 1.0) * 100.0
    return net_ret, equity, drawdown_pct, one_way_turnover


def compute_performance_metrics(
    daily_returns: np.ndarray,
    one_way_turnover: np.ndarray | None = None,
    strategy_name: str = "Strategy",
) -> dict[str, float | str]:
    """Compute CAGR, Vol, Sharpe, Sortino, Max Drawdown, Calmar, Total Return, and Turnover."""
    r = np.asarray(daily_returns, dtype=float)
    n_days = len(r)
    if n_days == 0:
        return {
            "Strategy": strategy_name,
            "CAGR (%)": 0.0,
            "Ann. Vol (%)": 0.0,
            "Sharpe": 0.0,
            "Sortino": 0.0,
            "Max Drawdown (%)": 0.0,
            "Calmar": 0.0,
            "Total Return (%)": 0.0,
            "Ann. Turnover (%)": 0.0,
        }

    equity = np.cumprod(1.0 + r)
    total_ret = float(equity[-1] - 1.0)
    years = max(n_days / 252.0, 1.0 / 252.0)
    cagr = float(equity[-1] ** (1.0 / years) - 1.0) if equity[-1] > 0 else -1.0

    mean_d = float(np.mean(r))
    std_d = float(np.std(r, ddof=1)) if n_days > 1 else 0.0
    ann_vol = std_d * np.sqrt(252.0)
    sharpe = (mean_d / std_d * np.sqrt(252.0)) if std_d > 1e-12 else 0.0

    downside = np.minimum(r, 0.0)
    downside_dev = float(np.sqrt(np.mean(downside**2)) * np.sqrt(252.0))
    sortino = (mean_d * 252.0 / downside_dev) if downside_dev > 1e-12 else 0.0

    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1.0
    max_dd = float(np.min(dd))
    calmar = (cagr / abs(max_dd)) if abs(max_dd) > 1e-12 else 0.0

    ann_turnover = (
        float(np.mean(one_way_turnover) * 252.0 * 100.0)
        if one_way_turnover is not None and len(one_way_turnover) > 0
        else 0.0
    )

    return {
        "Strategy": strategy_name,
        "CAGR (%)": round(cagr * 100.0, 2),
        "Ann. Vol (%)": round(ann_vol * 100.0, 2),
        "Sharpe": round(sharpe, 2),
        "Sortino": round(sortino, 2),
        "Max Drawdown (%)": round(max_dd * 100.0, 2),
        "Calmar": round(calmar, 2),
        "Total Return (%)": round(total_ret * 100.0, 2),
        "Ann. Turnover (%)": round(ann_turnover, 1),
    }


@dataclass
class BacktestResult:
    """Container for walk-forward backtest time series, weights, and summary metrics."""

    dates: pd.DatetimeIndex
    tickers: list[str]
    regime_weights_df: pd.DataFrame
    target_weights: np.ndarray
    applied_weights: np.ndarray
    turnover: np.ndarray
    curves_df: pd.DataFrame
    drawdowns_df: pd.DataFrame
    returns_df: pd.DataFrame
    metrics_df: pd.DataFrame


def run_walk_forward_backtest(
    features_df: pd.DataFrame,
    causal_proba: np.ndarray,
    smoother_proba: np.ndarray,
    tickers: Sequence[str] = ("SPY", "TLT", "GLD"),
    regime_weights: pd.DataFrame | np.ndarray | None = None,
    sizing_mode: str = "discrete",
    cost_bps: float = 5.0,
    forward_only_proba: np.ndarray | None = None,
) -> BacktestResult:
    """
    Run the causal walk-forward backtest (day t-1 signal -> day t return) and compare
    it against:
      - Forward-Filter HMM (Full-Sample Fit + Causal Alpha at t-1)
      - Look-Ahead Smoother HMM (Biased predict_proba at t, no lag)
      - Buy & Hold Primary Asset (e.g. SPY)
      - Static 60/40 Benchmark (60% Primary / 40% Defensive 1)
    """
    symbols = [str(t).strip().upper() for t in tickers if str(t).strip()]
    n_states = causal_proba.shape[1]

    if regime_weights is None:
        weights_df = default_regime_weights(n_states=n_states, tickers=symbols)
    elif isinstance(regime_weights, pd.DataFrame):
        weights_df = regime_weights.copy()
    else:
        meta = get_regime_metadata(n_states)
        weights_df = pd.DataFrame(
            np.asarray(regime_weights, dtype=float),
            index=[f"State {k}: {meta[k]['name']}" for k in range(n_states)],
            columns=symbols,
        )

    W_mat = weights_df.to_numpy(dtype=float)
    ret_cols = [f"ret_{s}" for s in symbols]
    asset_rets = features_df[ret_cols].to_numpy(dtype=float)

    # 1. Primary Causal Strategy (Walk-Forward or selected causal probability series, t-1 -> t)
    target_w, applied_w = compute_target_weights_from_proba(
        causal_proba, W_mat, sizing_mode=sizing_mode
    )
    strat_ret, strat_eq, strat_dd, strat_to = _simulate_portfolio(
        asset_rets, applied_w, cost_bps=cost_bps
    )

    # 2. Optional Full-Fit + Forward-Only Alpha Strategy (t-1 -> t)
    if forward_only_proba is not None:
        _, fwd_applied_w = compute_target_weights_from_proba(
            forward_only_proba, W_mat, sizing_mode=sizing_mode
        )
        fwd_ret, fwd_eq, fwd_dd, fwd_to = _simulate_portfolio(
            asset_rets, fwd_applied_w, cost_bps=cost_bps
        )
    else:
        fwd_ret, fwd_eq, fwd_dd, fwd_to = strat_ret, strat_eq, strat_dd, strat_to

    # 3. Look-Ahead Biased Smoother (uses predict_proba(X) at day t directly -- illustrates leak)
    smooth_target_w, _ = compute_target_weights_from_proba(
        smoother_proba, W_mat, sizing_mode=sizing_mode
    )
    smooth_ret, smooth_eq, smooth_dd, smooth_to = _simulate_portfolio(
        asset_rets, smooth_target_w, cost_bps=cost_bps
    )

    # 4. Benchmark: Buy & Hold Primary Asset (100% ticker[0])
    bh_w = np.zeros_like(applied_w)
    bh_w[:, 0] = 1.0
    bh_ret, bh_eq, bh_dd, bh_to = _simulate_portfolio(asset_rets, bh_w, cost_bps=0.0)

    # 5. Benchmark: Static 60/40 (60% ticker[0], 40% ticker[1] or split across defensives)
    b60_w = np.zeros_like(applied_w)
    if len(symbols) == 1:
        b60_w[:, 0] = 1.0
    else:
        b60_w[:, 0] = 0.60
        b60_w[:, 1] = 0.40
    b60_ret, b60_eq, b60_dd, b60_to = _simulate_portfolio(asset_rets, b60_w, cost_bps=0.0)

    primary_sym = symbols[0]
    def_sym = symbols[1] if len(symbols) > 1 else symbols[0]
    b60_label = f"Static 60/40 ({primary_sym}/{def_sym})"

    curves_df = pd.DataFrame(
        {
            "HMM Walk-Forward (No Look-Ahead)": strat_eq,
            "HMM Forward-Filter (Causal Alpha)": fwd_eq,
            f"Buy & Hold {primary_sym}": bh_eq,
            b60_label: b60_eq,
            "HMM Smoother (Look-Ahead Leak)": smooth_eq,
        },
        index=features_df.index,
    )

    drawdowns_df = pd.DataFrame(
        {
            "HMM Walk-Forward (No Look-Ahead)": strat_dd,
            "HMM Forward-Filter (Causal Alpha)": fwd_dd,
            f"Buy & Hold {primary_sym}": bh_dd,
            b60_label: b60_dd,
            "HMM Smoother (Look-Ahead Leak)": smooth_dd,
        },
        index=features_df.index,
    )

    returns_df = pd.DataFrame(
        {
            "HMM Walk-Forward (No Look-Ahead)": strat_ret,
            "HMM Forward-Filter (Causal Alpha)": fwd_ret,
            f"Buy & Hold {primary_sym}": bh_ret,
            b60_label: b60_ret,
            "HMM Smoother (Look-Ahead Leak)": smooth_ret,
        },
        index=features_df.index,
    )

    metrics_rows = [
        compute_performance_metrics(strat_ret, strat_to, "HMM Walk-Forward (No Look-Ahead)"),
        compute_performance_metrics(fwd_ret, fwd_to, "HMM Forward-Filter (Causal Alpha)"),
        compute_performance_metrics(bh_ret, bh_to, f"Buy & Hold {primary_sym}"),
        compute_performance_metrics(b60_ret, b60_to, b60_label),
        compute_performance_metrics(smooth_ret, smooth_to, "HMM Smoother (Look-Ahead Leak)"),
    ]
    metrics_df = pd.DataFrame(metrics_rows)

    return BacktestResult(
        dates=features_df.index,
        tickers=symbols,
        regime_weights_df=weights_df,
        target_weights=target_w,
        applied_weights=applied_w,
        turnover=strat_to,
        curves_df=curves_df,
        drawdowns_df=drawdowns_df,
        returns_df=returns_df,
        metrics_df=metrics_df,
    )


def build_export_dataframe(
    features_df: pd.DataFrame,
    causal_proba: np.ndarray,
    smoother_proba: np.ndarray,
    backtest_res: BacktestResult,
) -> pd.DataFrame:
    """
    Build a daily regime + allocation CSV DataFrame designed for downstream consumption
    by `@Portfolio Oversight` and `@Strategy Research`.
    """
    n_states = causal_proba.shape[1]
    meta = get_regime_metadata(n_states)
    causal_states = np.argmax(causal_proba, axis=1)
    smoother_states = np.argmax(smoother_proba, axis=1)

    export = pd.DataFrame(index=features_df.index)
    export.index.name = "date"

    for sym in backtest_res.tickers:
        price_col = f"price_{sym}"
        if price_col in features_df.columns:
            export[f"close_{sym}"] = np.round(features_df[price_col].to_numpy(), 4)

    export["log_return"] = np.round(features_df["log_return"].to_numpy(), 6)
    export["rolling_vol_ann"] = np.round(features_df["rolling_vol"].to_numpy(), 6)

    export["causal_regime_id"] = causal_states
    export["causal_regime_label"] = [meta[i]["name"] for i in causal_states]
    export["smoother_regime_id"] = smoother_states
    export["smoother_regime_label"] = [meta[i]["name"] for i in smoother_states]

    for k in range(n_states):
        slug = meta[k]["short"]
        export[f"prob_state_{k}_{slug}"] = np.round(causal_proba[:, k], 6)

    for j, sym in enumerate(backtest_res.tickers):
        export[f"target_weight_{sym}"] = np.round(backtest_res.target_weights[:, j], 4)
        export[f"applied_weight_{sym}"] = np.round(backtest_res.applied_weights[:, j], 4)

    primary_sym = backtest_res.tickers[0]
    export["strategy_daily_return"] = np.round(
        backtest_res.returns_df["HMM Walk-Forward (No Look-Ahead)"].to_numpy(), 6
    )
    export["strategy_equity"] = np.round(
        backtest_res.curves_df["HMM Walk-Forward (No Look-Ahead)"].to_numpy(), 6
    )
    export[f"buy_hold_{primary_sym}_equity"] = np.round(
        backtest_res.curves_df[f"Buy & Hold {primary_sym}"].to_numpy(), 6
    )

    return export.reset_index()
