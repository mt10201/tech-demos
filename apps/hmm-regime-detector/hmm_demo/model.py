"""Gaussian HMM fitting, deterministic volatility state sorting, and causal forward filtering."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from scipy.special import logsumexp
from threadpoolctl import threadpool_limits

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")


REGIME_PALETTES: dict[int, list[dict[str, str]]] = {
    2: [
        {"name": "Bull / Calm", "short": "bull_calm", "color": "#10b981", "fill": "rgba(16, 185, 129, 0.18)"},
        {"name": "Bear / High-Vol", "short": "bear_high_vol", "color": "#ef4444", "fill": "rgba(239, 68, 68, 0.20)"},
    ],
    3: [
        {"name": "Bull / Calm", "short": "bull_calm", "color": "#10b981", "fill": "rgba(16, 185, 129, 0.18)"},
        {"name": "Neutral / Transition", "short": "neutral_transition", "color": "#f59e0b", "fill": "rgba(245, 158, 11, 0.18)"},
        {"name": "Bear / High-Vol", "short": "bear_high_vol", "color": "#ef4444", "fill": "rgba(239, 68, 68, 0.20)"},
    ],
    4: [
        {"name": "Bull / Low-Vol", "short": "bull_low_vol", "color": "#10b981", "fill": "rgba(16, 185, 129, 0.18)"},
        {"name": "Mild Bull / Normal-Vol", "short": "mild_bull", "color": "#3b82f6", "fill": "rgba(59, 130, 246, 0.16)"},
        {"name": "Correction / Elevated-Vol", "short": "correction", "color": "#f59e0b", "fill": "rgba(245, 158, 11, 0.18)"},
        {"name": "Crisis / High-Vol", "short": "crisis_high_vol", "color": "#ef4444", "fill": "rgba(239, 68, 68, 0.22)"},
    ],
}


def get_regime_metadata(n_states: int = 3) -> list[dict[str, str]]:
    """Return human-readable regime names, slugs, and hex/rgba colors ordered from lowest to highest vol."""
    if n_states not in REGIME_PALETTES:
        raise ValueError(f"n_states must be one of {sorted(REGIME_PALETTES)}, got {n_states}.")
    return [dict(item) for item in REGIME_PALETTES[n_states]]


def sort_hmm_states_by_volatility(
    model: GaussianHMM,
    vol_col: int = 1,
    ret_col: int = 0,
) -> np.ndarray:
    """
    Deterministically permute a fitted GaussianHMM in-place so that state 0 has the
    lowest mean realized volatility (`means_[:, vol_col]`) and state K-1 has the highest.
    If two states tie on volatility to 1e-12, higher mean return (`-means_[:, ret_col]`) comes first.

    Returns the permutation index array `order` that was applied.
    """
    vols = np.round(model.means_[:, vol_col], 12)
    neg_rets = -model.means_[:, ret_col]
    order = np.lexsort((neg_rets, vols))

    model.startprob_ = np.asarray(model.startprob_[order], dtype=float)
    model.transmat_ = np.asarray(model.transmat_[np.ix_(order, order)], dtype=float)
    model.means_ = np.asarray(model.means_[order], dtype=float)
    model._covars_ = np.asarray(model._covars_[order], dtype=float)
    return order


def fit_gaussian_hmm(
    X: np.ndarray,
    n_states: int = 3,
    covariance_type: str = "full",
    n_iter: int = 150,
    tol: float = 1e-3,
    random_state: int = 42,
) -> GaussianHMM:
    """
    Fit a GaussianHMM on 2D feature matrix `X` (`[log_return, rolling_vol]`).
    Initializes states deterministically from volatility quantiles with a sticky diagonal
    transition prior so EM converges to persistent volatility regimes rather than oscillating
    single-day return noise, then rescales parameters back to raw feature units and sorts
    states by ascending realized volatility.
    """
    X_arr = np.asarray(X, dtype=float)
    if X_arr.ndim != 2 or X_arr.shape[1] < 2:
        raise ValueError("X must be a 2D array with at least 2 columns [log_return, rolling_vol].")
    if len(X_arr) < n_states * 5:
        raise ValueError(f"Need at least {n_states * 5} observations to fit a {n_states}-state HMM.")

    n_features = X_arr.shape[1]
    mu = X_arr.mean(axis=0)
    sd = X_arr.std(axis=0)
    sd = np.where(sd < 1e-12, 1.0, sd)
    X_z = (X_arr - mu) / sd

    # Deterministic quantile seeding on standardized rolling volatility (column 1)
    vol_z = X_z[:, 1]
    edges = np.quantile(vol_z, np.linspace(0.0, 1.0, n_states + 1))
    means_init = np.zeros((n_states, n_features), dtype=float)
    if covariance_type == "full":
        covars_init = np.zeros((n_states, n_features, n_features), dtype=float)
    else:
        covars_init = np.zeros((n_states, n_features), dtype=float)

    for k in range(n_states):
        if k < n_states - 1:
            mask = (vol_z >= edges[k]) & (vol_z <= edges[k + 1])
        else:
            mask = vol_z >= edges[k]
        sub_k = X_z[mask] if int(np.sum(mask)) >= 5 else X_z
        means_init[k] = sub_k.mean(axis=0)
        if covariance_type == "full":
            cov_k = np.atleast_2d(np.cov(sub_k.T))
            covars_init[k] = cov_k + np.eye(n_features) * 1e-2
        else:
            covars_init[k] = sub_k.var(axis=0) + 1e-2

    trans_init = np.full((n_states, n_states), 0.03 / max(n_states - 1, 1), dtype=float)
    np.fill_diagonal(trans_init, 0.97)
    start_init = np.full(n_states, 1.0 / n_states, dtype=float)

    model = GaussianHMM(
        n_components=n_states,
        covariance_type=covariance_type,
        min_covar=1e-3,
        n_iter=n_iter,
        tol=tol,
        init_params="",
        random_state=random_state,
    )
    model.startprob_ = start_init
    model.transmat_ = trans_init
    model.means_ = means_init
    model._covars_ = covars_init

    with threadpool_limits(limits=1):
        model.fit(X_z)

    # Transform Gaussian emission parameters back to raw feature units
    model.min_covar = 1e-10
    model.means_ = model.means_ * sd + mu
    if covariance_type == "full":
        scale_mat = np.outer(sd, sd)
        model._covars_ = np.array([cov * scale_mat for cov in model._covars_], dtype=float)
    elif covariance_type == "diag":
        model._covars_ = model._covars_ * (sd**2)[None, :]
    elif covariance_type == "tied":
        model._covars_ = model._covars_ * np.outer(sd, sd)
    elif covariance_type == "spherical":
        model._covars_ = model._covars_ * float(np.mean(sd**2))

    # Normalize transition rows in case of tiny floating-point drift
    row_sums = model.transmat_.sum(axis=1, keepdims=True)
    row_sums = np.where(row_sums <= 0, 1.0, row_sums)
    model.transmat_ = model.transmat_ / row_sums
    model.startprob_ = model.startprob_ / np.sum(model.startprob_)

    sort_hmm_states_by_volatility(model, vol_col=1, ret_col=0)
    return model


def forward_filter_proba(
    model: GaussianHMM,
    X: np.ndarray,
    initial_prob: np.ndarray | None = None,
) -> np.ndarray:
    """
    Compute causal forward-only filtered state probabilities:
        alpha_t(k) = P(S_t = k | X_{0:t})
    using only observations up to index t.

    Unlike `model.predict_proba(X)` (which runs the forward-backward Baum-Welch smoother
    and leaks future observations X_{t+1:T} via the backward beta pass), `forward_filter_proba`
    is strictly causal in X: perturbing X[t+1:] has zero effect on alpha[:t+1].
    """
    X_arr = np.asarray(X, dtype=float)
    n_samples = len(X_arr)
    n_states = model.n_components
    if n_samples == 0:
        return np.empty((0, n_states), dtype=float)

    log_B = model._compute_log_likelihood(X_arr)  # shape (T, K)
    log_A = np.log(np.clip(model.transmat_, 1e-300, 1.0))  # shape (K, K)

    if initial_prob is None:
        pi = np.asarray(model.startprob_, dtype=float)
    else:
        pi = np.asarray(initial_prob, dtype=float)
        pi = pi / np.sum(pi)

    log_pi = np.log(np.clip(pi, 1e-300, 1.0))

    log_alpha_hist = np.zeros((n_samples, n_states), dtype=float)

    # Step t = 0
    log_alpha = log_pi + log_B[0]
    log_alpha = log_alpha - logsumexp(log_alpha)
    log_alpha_hist[0] = log_alpha

    # Recursive causal forward filter for t = 1 ... T - 1
    for t in range(1, n_samples):
        log_prior = logsumexp(log_alpha[:, None] + log_A, axis=0)
        log_alpha = log_prior + log_B[t]
        log_alpha = log_alpha - logsumexp(log_alpha)
        log_alpha_hist[t] = log_alpha

    proba = np.exp(log_alpha_hist)
    proba /= proba.sum(axis=1, keepdims=True)
    return proba


@dataclass
class HMMRegimeResult:
    """Container for full-sample, forward-filtered, and walk-forward HMM outputs."""

    n_states: int
    model: GaussianHMM
    metadata: list[dict[str, str]]
    # Probabilities (T, K)
    walk_forward_proba: np.ndarray
    forward_only_proba: np.ndarray
    smoother_proba: np.ndarray
    # Discrete MAP / Viterbi state sequences (T,)
    walk_forward_states: np.ndarray
    forward_only_states: np.ndarray
    smoother_states: np.ndarray
    viterbi_states: np.ndarray
    # Walk-forward metadata
    min_train_days: int
    refit_every: int
    lookahead_stats: dict[str, float]


def walk_forward_hmm_inference(
    X: np.ndarray,
    n_states: int = 3,
    min_train_days: int = 504,
    refit_every: int = 63,
    covariance_type: str = "full",
    random_state: int = 42,
) -> HMMRegimeResult:
    """
    Compute:
      1. `walk_forward_proba`: Expanding-window out-of-sample HMM refit every `refit_every`
         days after `min_train_days`, combined with causal forward-only (`alpha`) filtering.
      2. `forward_only_proba`: Full-sample fitted HMM parameters + causal forward-only (`alpha`)
         filtering (no backward smoother pass).
      3. `smoother_proba` / `viterbi_states`: Standard `hmmlearn` `predict_proba(X)` and
         `predict(X)` which use future observations via the backward pass.
    """
    X_arr = np.asarray(X, dtype=float)
    n_samples = len(X_arr)
    eff_min_train = min(max(int(min_train_days), n_states * 20), max(n_samples - 1, n_states * 10))
    eff_step = max(int(refit_every), 10)

    # 1. Full-sample fit (sorted deterministically by vol)
    full_model = fit_gaussian_hmm(
        X_arr,
        n_states=n_states,
        covariance_type=covariance_type,
        random_state=random_state,
    )
    fwd_proba = forward_filter_proba(full_model, X_arr)
    smooth_proba = full_model.predict_proba(X_arr)
    vit_states = full_model.predict(X_arr)

    # 2. Expanding-window walk-forward refit + forward filter
    wf_proba = np.zeros((n_samples, n_states), dtype=float)
    if eff_min_train >= n_samples:
        wf_proba[:] = fwd_proba
    else:
        init_model = fit_gaussian_hmm(
            X_arr[:eff_min_train],
            n_states=n_states,
            covariance_type=covariance_type,
            random_state=random_state,
        )
        wf_proba[:eff_min_train] = forward_filter_proba(init_model, X_arr[:eff_min_train])

        for start in range(eff_min_train, n_samples, eff_step):
            end = min(start + eff_step, n_samples)
            step_model = fit_gaussian_hmm(
                X_arr[:start],
                n_states=n_states,
                covariance_type=covariance_type,
                random_state=random_state,
            )
            prev_post = wf_proba[start - 1]
            prior_start = prev_post @ step_model.transmat_
            prior_start = np.clip(prior_start, 1e-12, 1.0)
            prior_start /= prior_start.sum()
            wf_proba[start:end] = forward_filter_proba(
                step_model,
                X_arr[start:end],
                initial_prob=prior_start,
            )

    wf_states = np.argmax(wf_proba, axis=1)
    fwd_states = np.argmax(fwd_proba, axis=1)
    smooth_states = np.argmax(smooth_proba, axis=1)

    oos_slice = slice(eff_min_train, n_samples) if eff_min_train < n_samples else slice(0, n_samples)
    disagree_fwd_vs_smooth = float(np.mean(fwd_states != smooth_states) * 100.0)
    disagree_wf_vs_smooth = float(np.mean(wf_states[oos_slice] != smooth_states[oos_slice]) * 100.0)
    mean_l1_fwd_vs_smooth = float(np.mean(np.sum(np.abs(fwd_proba - smooth_proba), axis=1)))
    mean_l1_wf_vs_smooth = float(np.mean(np.sum(np.abs(wf_proba[oos_slice] - smooth_proba[oos_slice]), axis=1)))
    flip_days_fwd = int(np.sum(fwd_states != smooth_states))
    flip_days_wf = int(np.sum(wf_states != smooth_states))

    lookahead_stats = {
        "disagree_fwd_vs_smoother_pct": disagree_fwd_vs_smooth,
        "disagree_wf_vs_smoother_pct": disagree_wf_vs_smooth,
        "mean_l1_fwd_vs_smoother": mean_l1_fwd_vs_smooth,
        "mean_l1_wf_vs_smoother": mean_l1_wf_vs_smooth,
        "flip_days_fwd_vs_smoother": float(flip_days_fwd),
        "flip_days_wf_vs_smoother": float(flip_days_wf),
    }

    return HMMRegimeResult(
        n_states=n_states,
        model=full_model,
        metadata=get_regime_metadata(n_states),
        walk_forward_proba=wf_proba,
        forward_only_proba=fwd_proba,
        smoother_proba=smooth_proba,
        walk_forward_states=wf_states,
        forward_only_states=fwd_states,
        smoother_states=smooth_states,
        viterbi_states=vit_states,
        min_train_days=eff_min_train,
        refit_every=eff_step,
        lookahead_stats=lookahead_stats,
    )


def _empirical_average_duration(states: np.ndarray, target_state: int) -> float:
    """Compute the mean consecutive run length (in trading days) spent in `target_state`."""
    mask = np.asarray(states == target_state, dtype=int)
    if mask.sum() == 0:
        return 0.0
    padded = np.concatenate([[0], mask, [0]])
    diffs = np.diff(padded)
    starts = np.where(diffs == 1)[0]
    ends = np.where(diffs == -1)[0]
    lengths = ends - starts
    return float(np.mean(lengths)) if len(lengths) > 0 else 0.0


def compute_regime_summary_table(
    features_df: pd.DataFrame,
    states: np.ndarray,
    transmat: np.ndarray,
    n_states: int = 3,
    primary_ticker: str = "SPY",
) -> pd.DataFrame:
    """
    Build a per-regime summary table with:
      - Regime ID and label
      - Trading Days and % of Time
      - Annualized Return (%)
      - Annualized Volatility (%)
      - Mean Rolling Vol (%)
      - Annualized Sharpe Ratio
      - Empirical Avg Duration (days)
      - Implied Markov Duration 1 / (1 - A_kk) (days)
      - Self-Transition Probability A_kk (%)
    """
    meta = get_regime_metadata(n_states)
    ret_col = f"ret_{primary_ticker.strip().upper()}"
    if ret_col not in features_df.columns:
        simple_ret = np.exp(features_df["log_return"].to_numpy()) - 1.0
    else:
        simple_ret = features_df[ret_col].to_numpy()

    roll_vol = features_df["rolling_vol"].to_numpy()
    total_days = len(states)
    rows: list[dict[str, Any]] = []

    for k in range(n_states):
        mask = states == k
        n_k = int(np.sum(mask))
        pct_time = (n_k / total_days * 100.0) if total_days > 0 else 0.0

        if n_k > 1:
            r_k = simple_ret[mask]
            mean_daily = float(np.mean(r_k))
            std_daily = float(np.std(r_k, ddof=1))
            ann_ret = ((1.0 + mean_daily) ** 252 - 1.0) * 100.0
            ann_vol = std_daily * np.sqrt(252.0) * 100.0
            sharpe = (mean_daily / std_daily * np.sqrt(252.0)) if std_daily > 1e-12 else 0.0
            mean_roll_vol = float(np.mean(roll_vol[mask])) * 100.0
        elif n_k == 1:
            r_k = simple_ret[mask]
            ann_ret = float(r_k[0]) * 252.0 * 100.0
            ann_vol = float(roll_vol[mask][0]) * 100.0
            sharpe = 0.0
            mean_roll_vol = ann_vol
        else:
            ann_ret = 0.0
            ann_vol = 0.0
            sharpe = 0.0
            mean_roll_vol = 0.0

        emp_dur = _empirical_average_duration(states, k)
        p_stay = float(transmat[k, k])
        theo_dur = (1.0 / max(1.0 - p_stay, 1e-6)) if p_stay < 0.999999 else 999.0

        rows.append(
            {
                "State": k,
                "Regime": meta[k]["name"],
                "Days": n_k,
                "% of Time": round(pct_time, 1),
                "Ann. Return (%)": round(ann_ret, 2),
                "Ann. Vol (%)": round(ann_vol, 2),
                "Mean Rolling Vol (%)": round(mean_roll_vol, 2),
                "Sharpe": round(sharpe, 2),
                "Avg Duration (d)": round(emp_dur, 1),
                "Markov E[Duration] (d)": round(theo_dur, 1),
                "Stay Prob A_kk (%)": round(p_stay * 100.0, 1),
            }
        )

    return pd.DataFrame(rows)
