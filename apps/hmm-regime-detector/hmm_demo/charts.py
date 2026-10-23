"""Plotly visualizations for HMM regime detection, transition matrices, and walk-forward backtests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .backtest import BacktestResult
from .model import get_regime_metadata


def _contiguous_regime_spans(
    dates: pd.DatetimeIndex,
    states: np.ndarray,
) -> list[tuple[pd.Timestamp, pd.Timestamp, int]]:
    """Collapse a daily state array into contiguous (start_date, end_date, state) spans."""
    if len(dates) == 0:
        return []
    spans: list[tuple[pd.Timestamp, pd.Timestamp, int]] = []
    start_idx = 0
    curr_state = int(states[0])

    for i in range(1, len(states)):
        st = int(states[i])
        if st != curr_state:
            spans.append((dates[start_idx], dates[i], curr_state))
            start_idx = i
            curr_state = st
    spans.append((dates[start_idx], dates[-1], curr_state))
    return spans


def build_regime_price_and_prob_chart(
    features_df: pd.DataFrame,
    proba: np.ndarray,
    states: np.ndarray,
    primary_ticker: str = "SPY",
    n_states: int = 3,
    mode_label: str = "Walk-Forward Causal Filter",
    min_train_date: pd.Timestamp | None = None,
) -> go.Figure:
    """
    Build a 3-row synchronized Plotly figure:
      Row 1: Primary asset price chart with contiguous background shading by active HMM regime.
      Row 2: Stacked daily regime probability bands (0% - 100%).
      Row 3: Annualized rolling realized volatility (%) colored by regime threshold.
    """
    meta = get_regime_metadata(n_states)
    dates = features_df.index
    price_col = f"price_{primary_ticker.strip().upper()}"
    prices = features_df[price_col].to_numpy()
    roll_vol = features_df["rolling_vol"].to_numpy() * 100.0

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.50, 0.28, 0.22],
        subplot_titles=(
            f"{primary_ticker.upper()} Adjusted Close Shaded by Active Regime ({mode_label})",
            f"Daily Regime State Probabilities P(S_t = k) — {mode_label}",
            f"{primary_ticker.upper()} Annualized Rolling Realized Volatility (%)",
        ),
    )

    # Add dummy legend traces for regime background colors
    for k in range(n_states):
        fig.add_trace(
            go.Scatter(
                x=[dates[0]],
                y=[prices[0]],
                mode="lines",
                line=dict(color=meta[k]["color"], width=8),
                name=f"State {k}: {meta[k]['name']}",
                legendgroup=f"state_{k}",
                showlegend=True,
            ),
            row=1,
            col=1,
        )

    # Price line on Row 1
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=prices,
            mode="lines",
            line=dict(color="#f8fafc", width=2.0),
            name=f"{primary_ticker.upper()} Price",
            hovertemplate="%{x|%Y-%m-%d}<br>Price: $%{y:.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    # Contiguous background regime shading on Row 1
    spans = _contiguous_regime_spans(dates, states)
    shapes = []
    for x0, x1, st in spans:
        shapes.append(
            dict(
                type="rect",
                xref="x",
                yref="y domain",
                x0=x0,
                x1=x1,
                y0=0.0,
                y1=1.0,
                fillcolor=meta[st]["fill"],
                line=dict(width=0),
                layer="below",
            )
        )
    fig.update_layout(shapes=shapes)

    # Stacked regime probabilities on Row 2
    for k in range(n_states):
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=proba[:, k] * 100.0,
                mode="lines",
                line=dict(width=0.6, color=meta[k]["color"]),
                stackgroup="prob_stack",
                fillcolor=meta[k]["color"],
                name=f"P({meta[k]['name']})",
                legendgroup=f"state_{k}",
                showlegend=False,
                hovertemplate=f"%{{x|%Y-%m-%d}}<br>{meta[k]['name']}: %{{y:.1f}}%<extra></extra>",
            ),
            row=2,
            col=1,
        )

    # Rolling volatility on Row 3
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=roll_vol,
            mode="lines",
            line=dict(color="#38bdf8", width=1.6),
            fill="tozeroy",
            fillcolor="rgba(56, 189, 248, 0.15)",
            name="Rolling Vol (%)",
            hovertemplate="%{x|%Y-%m-%d}<br>Rolling Vol: %{y:.1f}%<extra></extra>",
        ),
        row=3,
        col=1,
    )

    if min_train_date is not None and dates[0] < min_train_date < dates[-1]:
        for r in (1, 2, 3):
            fig.add_vline(
                x=min_train_date,
                line_width=1.5,
                line_dash="dash",
                line_color="#e2e8f0",
                row=r,
                col=1,
            )
        fig.add_annotation(
            x=min_train_date,
            y=1.02,
            xref="x",
            yref="y domain",
            text="Out-of-Sample Walk-Forward Start →",
            showarrow=False,
            xanchor="left",
            font=dict(size=11, color="#e2e8f0"),
        )

    fig.update_yaxes(title_text="Price ($)", row=1, col=1, gridcolor="rgba(148,163,184,0.15)")
    fig.update_yaxes(title_text="Prob (%)", range=[0, 100], row=2, col=1, gridcolor="rgba(148,163,184,0.15)")
    fig.update_yaxes(title_text="Ann. Vol (%)", row=3, col=1, gridcolor="rgba(148,163,184,0.15)")
    fig.update_xaxes(gridcolor="rgba(148,163,184,0.12)")

    fig.update_layout(
        template="plotly_dark",
        height=760,
        margin=dict(l=60, r=30, t=70, b=45),
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.04,
            xanchor="left",
            x=0.0,
            bgcolor="rgba(15, 23, 42, 0.8)",
        ),
        hovermode="x unified",
    )
    return fig


def build_transition_matrix_heatmap(
    transmat: np.ndarray,
    n_states: int = 3,
) -> go.Figure:
    """Build an annotated Plotly heatmap of the Markov transition probability matrix A_{i,j}."""
    meta = get_regime_metadata(n_states)
    labels = [f"S{k}: {meta[k]['name']}" for k in range(n_states)]
    pct_mat = np.asarray(transmat, dtype=float) * 100.0
    text_mat = [[f"{val:.1f}%" for val in row] for row in pct_mat]

    fig = go.Figure(
        data=go.Heatmap(
            z=pct_mat,
            x=[f"To {lbl}" for lbl in labels],
            y=[f"From {lbl}" for lbl in labels],
            text=text_mat,
            texttemplate="%{text}",
            textfont=dict(size=14, color="#f8fafc"),
            colorscale=[
                [0.0, "#1e293b"],
                [0.25, "#0369a1"],
                [0.65, "#0284c7"],
                [1.0, "#10b981"],
            ],
            zmin=0.0,
            zmax=100.0,
            colorbar=dict(title="Prob (%)"),
            hovertemplate="%{y} → %{x}: %{z:.2f}%<extra></extra>",
        )
    )

    fig.update_layout(
        title="Markov Transition Probability Matrix A(i → j)",
        template="plotly_dark",
        height=390,
        margin=dict(l=50, r=30, t=55, b=45),
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
        yaxis=dict(autorange="reversed"),
    )
    return fig


def build_lookahead_comparison_chart(
    dates: pd.DatetimeIndex,
    causal_proba: np.ndarray,
    smoother_proba: np.ndarray,
    n_states: int = 3,
    window_days: int = 504,
) -> go.Figure:
    """
    Compare the Risk-Off (highest-volatility state K-1) probability from the causal
    forward-only filter vs. `hmmlearn`'s full-sample smoother (`predict_proba`) over
    the most recent `window_days` trading days to visualize look-ahead leakage.
    """
    meta = get_regime_metadata(n_states)
    risk_off_idx = n_states - 1
    risk_off_name = meta[risk_off_idx]["name"]

    sl = slice(-min(window_days, len(dates)), None)
    d_sub = dates[sl]
    c_prob = causal_proba[sl, risk_off_idx] * 100.0
    s_prob = smoother_proba[sl, risk_off_idx] * 100.0
    diff = s_prob - c_prob

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.62, 0.38],
        subplot_titles=(
            f"Risk-Off Regime Probability P({risk_off_name}): Causal Filter vs. Biased Smoother",
            "Look-Ahead Leakage: Smoother P(Risk-Off) minus Causal P(Risk-Off) (%)",
        ),
    )

    fig.add_trace(
        go.Scatter(
            x=d_sub,
            y=s_prob,
            mode="lines",
            line=dict(color="#f43f5e", width=2.0, dash="dot"),
            name="Biased Smoother predict_proba (Uses Future Data)",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=d_sub,
            y=c_prob,
            mode="lines",
            line=dict(color="#10b981", width=2.0),
            name="Causal Forward Filter (No Future Data)",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            x=d_sub,
            y=diff,
            marker_color=np.where(diff >= 0, "#f43f5e", "#38bdf8"),
            name="Look-Ahead Delta (%)",
        ),
        row=2,
        col=1,
    )

    fig.update_yaxes(title_text="Prob (%)", range=[0, 102], row=1, col=1, gridcolor="rgba(148,163,184,0.15)")
    fig.update_yaxes(title_text="Delta (%)", row=2, col=1, gridcolor="rgba(148,163,184,0.15)")
    fig.update_layout(
        template="plotly_dark",
        height=430,
        margin=dict(l=55, r=30, t=60, b=40),
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="left", x=0.0),
        hovermode="x unified",
    )
    return fig


def build_backtest_equity_and_drawdown_chart(
    bt: BacktestResult,
    show_smoother_leak: bool = True,
) -> go.Figure:
    """
    Build a 3-row synchronized Plotly figure for the walk-forward backtest:
      Row 1: Cumulative growth of $1.00 (Equity curves: Walk-Forward HMM vs Buy-and-Hold vs 60/40 vs Biased Smoother).
      Row 2: Underwater drawdown (%) curves.
      Row 3: Stacked daily applied asset weights (t-1 signal applied at day t).
    """
    dates = bt.dates
    primary_sym = bt.tickers[0]
    def_sym = bt.tickers[1] if len(bt.tickers) > 1 else bt.tickers[0]
    b60_label = f"Static 60/40 ({primary_sym}/{def_sym})"

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.46, 0.28, 0.26],
        subplot_titles=(
            "Cumulative Portfolio Growth ($1.00 Initial Capital — Log/Linear Equity Curves)",
            "Underwater Drawdown from Peak (%)",
            "Applied Portfolio Asset Weights w_{t} (Signal Known at Close of Day t-1)",
        ),
    )

    series_styles = [
        ("HMM Walk-Forward (No Look-Ahead)", "#10b981", 2.8, "solid"),
        ("HMM Forward-Filter (Causal Alpha)", "#38bdf8", 1.9, "solid"),
        (f"Buy & Hold {primary_sym}", "#f59e0b", 2.0, "solid"),
        (b60_label, "#94a3b8", 1.8, "dash"),
    ]
    if show_smoother_leak:
        series_styles.append(("HMM Smoother (Look-Ahead Leak)", "#f43f5e", 1.8, "dot"))

    for col_name, color, width, dash in series_styles:
        if col_name not in bt.curves_df.columns:
            continue
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=bt.curves_df[col_name],
                mode="lines",
                line=dict(color=color, width=width, dash=dash),
                name=col_name,
                legendgroup=col_name,
                hovertemplate=f"%{{x|%Y-%m-%d}}<br>{col_name}: $%{{y:.2f}}<extra></extra>",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=bt.drawdowns_df[col_name],
                mode="lines",
                line=dict(color=color, width=max(width - 0.5, 1.3), dash=dash),
                name=f"{col_name} DD",
                legendgroup=col_name,
                showlegend=False,
                hovertemplate=f"%{{x|%Y-%m-%d}}<br>{col_name} DD: %{{y:.1f}}%<extra></extra>",
            ),
            row=2,
            col=1,
        )

    asset_colors = ["#3b82f6", "#10b981", "#f59e0b", "#a855f7", "#ec4899"]
    for j, sym in enumerate(bt.tickers):
        c = asset_colors[j % len(asset_colors)]
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=bt.applied_weights[:, j] * 100.0,
                mode="lines",
                line=dict(width=0.6, color=c),
                stackgroup="asset_weights",
                fillcolor=c,
                name=f"Weight: {sym}",
                hovertemplate=f"%{{x|%Y-%m-%d}}<br>{sym} Weight: %{{y:.1f}}%<extra></extra>",
            ),
            row=3,
            col=1,
        )

    fig.update_yaxes(title_text="Equity ($)", row=1, col=1, gridcolor="rgba(148,163,184,0.15)")
    fig.update_yaxes(title_text="Drawdown (%)", row=2, col=1, gridcolor="rgba(148,163,184,0.15)")
    fig.update_yaxes(title_text="Weight (%)", range=[0, 100], row=3, col=1, gridcolor="rgba(148,163,184,0.15)")
    fig.update_xaxes(gridcolor="rgba(148,163,184,0.12)")

    fig.update_layout(
        template="plotly_dark",
        height=760,
        margin=dict(l=60, r=30, t=70, b=45),
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.04,
            xanchor="left",
            x=0.0,
            bgcolor="rgba(15, 23, 42, 0.8)",
        ),
        hovermode="x unified",
    )
    return fig
