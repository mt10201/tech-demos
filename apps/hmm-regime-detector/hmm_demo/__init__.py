"""Gaussian HMM market-regime detector demo package."""

from .data import (
    HISTORY_WINDOWS,
    compute_features,
    fetch_prices,
    generate_synthetic_prices,
    load_bundled_prices,
    normalize_tickers,
)
from .model import (
    HMMRegimeResult,
    compute_regime_summary_table,
    fit_gaussian_hmm,
    forward_filter_proba,
    get_regime_metadata,
    sort_hmm_states_by_volatility,
    walk_forward_hmm_inference,
)
from .backtest import (
    BacktestResult,
    build_export_dataframe,
    compute_performance_metrics,
    compute_target_weights_from_proba,
    default_regime_weights,
    run_walk_forward_backtest,
)
from .charts import (
    build_backtest_equity_and_drawdown_chart,
    build_lookahead_comparison_chart,
    build_regime_price_and_prob_chart,
    build_transition_matrix_heatmap,
)

__all__ = [
    "HISTORY_WINDOWS",
    "compute_features",
    "fetch_prices",
    "generate_synthetic_prices",
    "load_bundled_prices",
    "normalize_tickers",
    "HMMRegimeResult",
    "compute_regime_summary_table",
    "fit_gaussian_hmm",
    "forward_filter_proba",
    "get_regime_metadata",
    "sort_hmm_states_by_volatility",
    "walk_forward_hmm_inference",
    "BacktestResult",
    "build_export_dataframe",
    "compute_performance_metrics",
    "compute_target_weights_from_proba",
    "default_regime_weights",
    "run_walk_forward_backtest",
    "build_backtest_equity_and_drawdown_chart",
    "build_lookahead_comparison_chart",
    "build_regime_price_and_prob_chart",
    "build_transition_matrix_heatmap",
]
