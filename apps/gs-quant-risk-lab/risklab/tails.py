"""Fat-tail statistics on daily simple returns (descriptive, over the selected sample)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def excess_kurtosis(r: pd.Series) -> float:
    r = r.dropna()
    return float(stats.kurtosis(r, fisher=True, bias=False)) if len(r) > 3 else float("nan")


def hill_curve(r: pd.Series, tail: str = "left", k_max_frac: float = 0.15, k_min: int = 10) -> pd.Series:
    """Hill tail-index estimate alpha(k) for k = k_min..k_max (k largest losses, or gains for tail='right').

    alpha(k) = 1 / ( mean_{i<=k} log X_(i) - log X_(k+1) ), X sorted descending, X > 0.
    alpha < 2 => infinite variance (Levy-stable territory); alpha ~ 3-4 is typical for equities.
    """
    x = -r.dropna().values if tail == "left" else r.dropna().values
    x = np.sort(x[x > 0])[::-1]
    n = len(x)
    k_max = min(int(n * k_max_frac), n - 1)
    if k_max < k_min:
        return pd.Series(dtype=float)
    logx = np.log(x)
    csum = np.cumsum(logx)
    ks = np.arange(k_min, k_max + 1)
    inv = csum[ks - 1] / ks - logx[ks]
    return pd.Series(1.0 / inv, index=pd.Index(ks, name="k"), name=r.name)


def hill_point(r: pd.Series, tail: str = "left", frac: float = 0.05) -> tuple[float, int]:
    """Hill alpha at k = frac * n_tail (default top 5% of observations) and the median over k in [2.5%, 10%]."""
    curve = hill_curve(r, tail)
    if curve.empty:
        return float("nan"), 0
    n = len(r.dropna())
    k = int(np.clip(round(frac * n), curve.index.min(), curve.index.max()))
    return float(curve.loc[k]), k


def hist_cvar(r: pd.Series, level: float = 0.95) -> float:
    """Historical CVaR / expected shortfall: average loss on the worst (1-level) share of days. Positive = loss."""
    x = np.sort(r.dropna().values)
    if len(x) == 0:
        return float("nan")
    n_tail = max(1, int(np.floor(len(x) * (1 - level))))
    return float(-x[:n_tail].mean())


def block_bootstrap_cvar(r: pd.Series, level: float = 0.95, block: int = 10, n_boot: int = 1000,
                         seed: int = 0) -> dict:
    """Moving-block bootstrap of CVaR (keeps volatility clustering within blocks). Returns mean and 5/95% bounds."""
    x = r.dropna().values
    n = len(x)
    if n < block * 2:
        return {"mean": float("nan"), "p05": float("nan"), "p95": float("nan")}
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(n_boot, n_blocks))
    offs = np.arange(block)
    samples = x[(starts[:, :, None] + offs).reshape(n_boot, -1)[:, :n]]
    n_tail = max(1, int(np.floor(n * (1 - level))))
    worst = np.sort(samples, axis=1)[:, :n_tail]
    cv = -worst.mean(axis=1)
    return {"mean": float(cv.mean()), "p05": float(np.percentile(cv, 5)), "p95": float(np.percentile(cv, 95))}


def drawdown_stats(r: pd.Series) -> dict:
    """Max drawdown, its peak/trough dates, and the longest time under water (trading days, peak to recovery)."""
    r = r.dropna()
    if r.empty:
        return {}
    idx = (1 + r).cumprod()
    peak = idx.cummax()
    dd = idx / peak - 1
    trough = dd.idxmin()
    peak_date = idx.loc[:trough].idxmax()
    under = (dd < 0).astype(int).values
    longest = cur = 0
    for u in under:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    return {
        "max_drawdown": float(dd.min()),
        "peak": peak_date,
        "trough": trough,
        "longest_underwater_days": int(longest),
        "current_drawdown": float(dd.iloc[-1]),
    }


def stable_fit(r: pd.Series) -> dict:
    """Levy-stable parameters via McCulloch's quantile estimator (scipy). alpha=2 is Gaussian; lower = fatter tails."""
    from scipy.stats import levy_stable

    x = r.dropna().values
    if len(x) < 100:
        return {}
    try:
        a, b, loc, scale = levy_stable._fitstart(x)  # fast quantile method; full MLE is too slow for a UI
    except Exception:  # pragma: no cover - private API fallback
        a, b, loc, scale = levy_stable.fit(x)
    return {"alpha": float(a), "beta": float(b), "loc": float(loc), "scale": float(scale)}


def tail_prob_table(r: pd.Series, fit: dict, sigmas=(3, 4, 5)) -> pd.DataFrame:
    """P(daily return <= mean - k*sd): empirical vs Gaussian vs fitted stable. Shows how much Gaussians under-count."""
    from scipy.stats import levy_stable

    x = r.dropna()
    mu, sd = x.mean(), x.std(ddof=1)
    rows = []
    for k in sigmas:
        thr = mu - k * sd
        row = {"move": f"<= -{k} sd ({thr:.2%})", "empirical": float((x <= thr).mean()),
               "gaussian": float(stats.norm.cdf(-k))}
        if fit:
            row["stable"] = float(levy_stable.cdf(thr, fit["alpha"], fit["beta"], fit["loc"], fit["scale"]))
        row["empirical_days"] = int((x <= thr).sum())
        row["gaussian_expected_days"] = float(stats.norm.cdf(-k) * len(x))
        rows.append(row)
    return pd.DataFrame(rows).set_index("move")


def tail_summary(returns: pd.DataFrame, block: int = 10, n_boot: int = 1000) -> pd.DataFrame:
    rows = []
    for c in returns.columns:
        r = returns[c].dropna()
        if len(r) < 60:
            continue
        hl, kl = hill_point(r, "left")
        hr, _ = hill_point(r, "right")
        b95 = block_bootstrap_cvar(r, 0.95, block, n_boot)
        b99 = block_bootstrap_cvar(r, 0.99, block, n_boot)
        dd = drawdown_stats(r)
        rows.append({
            "series": c, "days": len(r),
            "excess_kurtosis": excess_kurtosis(r), "skew": float(stats.skew(r)),
            "hill_alpha_left": hl, "hill_alpha_right": hr, "hill_k": kl,
            "cvar95_hist": hist_cvar(r, 0.95), "cvar95_boot": b95["mean"],
            "cvar95_boot_p05": b95["p05"], "cvar95_boot_p95": b95["p95"],
            "cvar99_hist": hist_cvar(r, 0.99), "cvar99_boot": b99["mean"],
            "cvar99_boot_p05": b99["p05"], "cvar99_boot_p95": b99["p95"],
            "max_drawdown": dd["max_drawdown"], "mdd_peak": dd["peak"].date(), "mdd_trough": dd["trough"].date(),
            "longest_underwater_days": dd["longest_underwater_days"],
            "current_drawdown": dd["current_drawdown"],
        })
    return pd.DataFrame(rows).set_index("series") if rows else pd.DataFrame()
