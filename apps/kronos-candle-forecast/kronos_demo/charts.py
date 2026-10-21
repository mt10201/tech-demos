"""Plotly figure: history candles, forecast band + median candles, optional actuals."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .forecast import Forecast


def forecast_figure(history: pd.DataFrame, fc: Forecast, actual: pd.DataFrame | None = None,
                    title: str = "", session: bool = False, interval: str = "1h",
                    show_paths: int = 0) -> go.Figure:
    fig = go.Figure()
    x_future = fc.median["timestamps"]

    # 10-90 and 25-75 percentile bands on close (drawn first, underneath candles)
    for lo, hi, alpha, name in ((10, 90, 0.16, "10-90% band (close)"), (25, 75, 0.28, "25-75% band (close)")):
        fig.add_trace(go.Scatter(x=x_future, y=fc.q[hi], mode="lines", line=dict(width=0),
                                 hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(x=x_future, y=fc.q[lo], mode="lines", line=dict(width=0),
                                 fill="tonexty", fillcolor=f"rgba(255,140,0,{alpha})", name=name,
                                 hovertemplate=f"{lo}th pct: %{{y:.4g}}<extra></extra>"))

    for i in range(min(show_paths, fc.paths.shape[0])):
        fig.add_trace(go.Scatter(x=x_future, y=fc.paths[i, :, 3], mode="lines",
                                 line=dict(width=0.7, color="rgba(255,140,0,0.35)"),
                                 hoverinfo="skip", showlegend=(i == 0), name="sampled paths"))

    fig.add_trace(go.Candlestick(
        x=history["timestamps"], open=history["open"], high=history["high"],
        low=history["low"], close=history["close"], name="history",
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350"))

    if actual is not None and len(actual):
        fig.add_trace(go.Candlestick(
            x=actual["timestamps"], open=actual["open"], high=actual["high"],
            low=actual["low"], close=actual["close"], name="actual (after cutoff)",
            increasing_line_color="#1e88e5", decreasing_line_color="#8e24aa",
            increasing_fillcolor="rgba(30,136,229,0.55)", decreasing_fillcolor="rgba(142,36,170,0.55)"))

    m = fc.median
    backtest = actual is not None and len(actual) > 0
    if not backtest:  # in backtest the actual candles sit there; median is drawn as a line only
        fig.add_trace(go.Candlestick(
            x=m["timestamps"], open=m["open"], high=m["high"], low=m["low"], close=m["close"],
            name="Kronos median forecast",
            increasing_line_color="#ff8c00", decreasing_line_color="#e65100",
            increasing_fillcolor="rgba(255,140,0,0.35)", decreasing_fillcolor="rgba(230,81,0,0.6)"))
    fig.add_trace(go.Scatter(x=m["timestamps"], y=m["close"],
                             mode="lines+markers" if backtest else "lines",
                             marker=dict(size=4),
                             line=dict(color="#e65100" if backtest else "#ff8c00",
                                       width=2.4 if backtest else 1.6, dash="solid" if backtest else "dot"),
                             name="Kronos median close" if backtest else "median close"))

    cutoff = history["timestamps"].iloc[-1]
    fig.add_shape(type="line", x0=cutoff, x1=cutoff, y0=0, y1=1, yref="paper",
                  line=dict(color="gray", width=1, dash="dash"))
    fig.add_annotation(x=cutoff, y=1, yref="paper", text="forecast starts", showarrow=False,
                       xanchor="right", yanchor="bottom", font=dict(size=11, color="gray"))

    breaks = []
    if session:
        breaks.append(dict(bounds=["sat", "mon"]))
        if interval != "1d":
            ts = pd.concat([history["timestamps"], m["timestamps"]])
            hrs = ts.dt.hour + ts.dt.minute / 60.0
            step_h = {"5m": 5 / 60, "15m": 0.25, "1h": 1.0}.get(interval, 1.0)
            breaks.append(dict(bounds=[float(hrs.max()) + step_h, float(hrs.min())], pattern="hour"))
    fig.update_layout(
        title=title, height=620, template="plotly_white", xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(l=10, r=10, t=80, b=10), hovermode="x unified",
    )
    fig.update_xaxes(rangebreaks=breaks)
    return fig
