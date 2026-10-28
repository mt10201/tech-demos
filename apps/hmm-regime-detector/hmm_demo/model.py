"""Gaussian HMM fitting, deterministic volatility state sorting, and causal forward filtering."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from scipy.optimize import minimize_scalar
from scipy.special import digamma, gammaln, logsumexp
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
    if hasattr(model, "dof_"):
        model.dof_ = np.asarray(model.dof_[order], dtype=float)
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


class StudentTHMM:
    """
    Hidden Markov Model with Multivariate Student-t emissions (Peel & McLachlan EM).

    Replaces the quadratic Gaussian Mahalanobis log-density with the heavy-tailed
    Multivariate Student-t log-density:
        ln f_t(x_t | s_t = k) = ln Gamma((nu_k + d)/2) - ln Gamma(nu_k/2)
            - (d/2) ln(pi * nu_k) - 0.5 ln|S_k|
            - ((nu_k + d)/2) ln(1 + (x_t - mu_k)^T S_k^{-1} (x_t - mu_k) / nu_k)

    During the E-step, extreme single-day return outliers receive a reduced latent
    precision weight w_{t,k} = (nu_k + d) / (nu_k + D_{t,k}^2), preventing single-day
    fat-tailed candles from corrupting state covariance estimates or whipsawing the
    causal forward filter unless volatility persistence confirms a regime shift.
    """

    def __init__(
        self,
        n_components: int = 3,
        covariance_type: str = "full",
        df_nu: float = 5.0,
        estimate_nu: bool = False,
        nu_bounds: tuple[float, float] = (3.5, 25.0),
        n_iter: int = 25,
        tol: float = 1e-2,
        random_state: int = 42,
    ) -> None:
        self.n_components = int(n_components)
        self.covariance_type = str(covariance_type)
        self.df_nu = float(df_nu)
        self.estimate_nu = bool(estimate_nu)
        self.nu_bounds = (float(nu_bounds[0]), float(nu_bounds[1]))
        self.n_iter = int(n_iter)
        self.tol = float(tol)
        self.random_state = int(random_state)

        self.startprob_: np.ndarray = np.full(self.n_components, 1.0 / self.n_components)
        self.transmat_: np.ndarray = np.eye(self.n_components)
        self.means_: np.ndarray = np.zeros((self.n_components, 2))
        self._covars_: np.ndarray = np.repeat(np.eye(2)[None, :, :], self.n_components, axis=0)
        self.dof_: np.ndarray = np.full(self.n_components, self.df_nu, dtype=float)

    @property
    def covars_(self) -> np.ndarray:
        """Return effective covariance matrices Sigma_k = (nu_k / (nu_k - 2)) * S_k."""
        K = self.n_components
        out = np.empty_like(self._covars_)
        for k in range(K):
            nu_k = max(float(self.dof_[k]), 2.05)
            factor = nu_k / (nu_k - 2.0)
            out[k] = self._covars_[k] * factor
        return out

    def _mahalanobis_and_logdet(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Compute squared Mahalanobis distance D_{t,k}^2 and log|S_k| for all states k."""
        X_arr = np.asarray(X, dtype=float)
        T, d = X_arr.shape
        K = self.n_components
        D2 = np.zeros((T, K), dtype=float)
        logdet = np.zeros(K, dtype=float)
        for k in range(K):
            S_k = np.asarray(self._covars_[k], dtype=float)
            if S_k.ndim == 1:
                S_k = np.diag(S_k)
            diag_scale = np.maximum(np.diag(S_k), 1e-10)
            S_k = 0.5 * (S_k + S_k.T) + np.diag(1e-6 * diag_scale + 1e-10)
            sign, ld = np.linalg.slogdet(S_k)
            if sign <= 0:
                S_k = S_k + np.diag(1e-3 * diag_scale + 1e-8)
                _, ld = np.linalg.slogdet(S_k)
            logdet[k] = ld
            inv_S = np.linalg.inv(S_k)
            diff = X_arr - self.means_[k]
            D2[:, k] = np.maximum(np.einsum("ti,ij,tj->t", diff, inv_S, diff), 0.0)
        return D2, logdet

    def _compute_log_likelihood(self, X: np.ndarray) -> np.ndarray:
        """Evaluate Multivariate Student-t log emission density ln f_t(x_t | s_t = k)."""
        X_arr = np.asarray(X, dtype=float)
        T, d = X_arr.shape
        K = self.n_components
        D2, logdet = self._mahalanobis_and_logdet(X_arr)
        log_B = np.zeros((T, K), dtype=float)
        for k in range(K):
            nu_k = max(float(self.dof_[k]), 2.05)
            const = (
                gammaln(0.5 * (nu_k + d))
                - gammaln(0.5 * nu_k)
                - 0.5 * d * np.log(np.pi * nu_k)
                - 0.5 * logdet[k]
            )
            log_B[:, k] = const - 0.5 * (nu_k + d) * np.log1p(D2[:, k] / nu_k)
        return log_B

    def _forward_backward(self, X_arr: np.ndarray) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
        """Run scaled Rabiner forward-backward algorithm; return (loglik, gamma, xi_sum, log_B)."""
        T, _ = X_arr.shape
        K = self.n_components
        log_B = self._compute_log_likelihood(X_arr)
        row_max = np.max(log_B, axis=1, keepdims=True)
        B = np.exp(log_B - row_max)

        pi0 = np.clip(np.asarray(self.startprob_, dtype=float), 1e-12, None)
        pi0 = pi0 / pi0.sum()
        A = np.clip(np.asarray(self.transmat_, dtype=float), 1e-12, None)
        A = A / A.sum(axis=1, keepdims=True)
        A_T = A.T.copy()

        alpha = np.zeros((T, K), dtype=float)
        scales = np.zeros(T, dtype=float)
        a0 = pi0 * B[0]
        c0 = float(a0.sum())
        if c0 < 1e-300:
            c0 = 1e-300
        alpha[0] = a0 / c0
        scales[0] = c0

        for t in range(1, T):
            at = (alpha[t - 1] @ A) * B[t]
            ct = float(at.sum())
            if ct < 1e-300:
                ct = 1e-300
            alpha[t] = at / ct
            scales[t] = ct

        loglik = float(np.sum(np.log(scales) + row_max[:, 0]))

        beta = np.zeros((T, K), dtype=float)
        beta[-1] = 1.0
        for t in range(T - 2, -1, -1):
            bt = (B[t + 1] * beta[t + 1]) @ A_T
            beta[t] = bt / scales[t + 1]

        gamma = alpha * beta
        gamma_sum = np.maximum(gamma.sum(axis=1, keepdims=True), 1e-300)
        gamma = gamma / gamma_sum

        b_beta = (B[1:] * beta[1:]) / scales[1:, None]
        xi_sum = (alpha[:-1].T @ b_beta) * A

        return loglik, gamma, xi_sum, log_B

    def fit(self, X: np.ndarray) -> "StudentTHMM":
        """Fit Student-t HMM via EM in standardized feature space, then rescale to raw units."""
        X_arr = np.asarray(X, dtype=float)
        T, d = X_arr.shape
        K = self.n_components

        mu_global = X_arr.mean(axis=0)
        sd_global = X_arr.std(axis=0)
        sd_global = np.where(sd_global < 1e-12, 1.0, sd_global)
        X_z = (X_arr - mu_global) / sd_global

        # Warm-start from GaussianHMM fitted on X_z
        g_model = fit_gaussian_hmm(
            X_z,
            n_states=K,
            covariance_type=self.covariance_type,
            n_iter=min(100, self.n_iter),
            tol=self.tol,
            random_state=self.random_state,
        )
        self.startprob_ = np.asarray(g_model.startprob_, dtype=float).copy()
        self.transmat_ = np.asarray(g_model.transmat_, dtype=float).copy()
        self.means_ = np.asarray(g_model.means_, dtype=float).copy()

        nu_init = max(self.df_nu, 2.5)
        scale_factor = (nu_init - 2.0) / nu_init
        g_covs = np.asarray(g_model._covars_, dtype=float)
        self._covars_ = np.zeros((K, d, d), dtype=float)
        for k in range(K):
            c_k = g_covs[k] if g_covs[k].ndim == 2 else np.diag(g_covs[k])
            self._covars_[k] = c_k * scale_factor + 1e-3 * np.eye(d)
        self.dof_ = np.full(K, nu_init, dtype=float)

        prev_ll = -np.inf
        for _ in range(self.n_iter):
            ll, gamma, xi_sum, _ = self._forward_backward(X_z)
            D2, _ = self._mahalanobis_and_logdet(X_z)

            # Latent Gamma precision weights w_{t,k} = E[u_{t,k} | x_t, s_t = k]
            w = np.zeros((T, K), dtype=float)
            for k in range(K):
                nu_k = float(self.dof_[k])
                w[:, k] = (nu_k + d) / (nu_k + D2[:, k])

            # M-step: startprob and sticky transmat prior
            sp = gamma[0] + 1e-4
            self.startprob_ = sp / sp.sum()

            tm = xi_sum + 1e-2 * np.eye(K) + 1e-5
            self.transmat_ = tm / tm.sum(axis=1, keepdims=True)

            # M-step: precision-weighted means and scale matrices S_k
            gw = gamma * w
            for k in range(K):
                gw_sum = max(float(gw[:, k].sum()), 1e-12)
                g_sum = max(float(gamma[:, k].sum()), 1e-12)
                mu_k = (gw[:, k][:, None] * X_z).sum(axis=0) / gw_sum
                self.means_[k] = mu_k
                diff = X_z - mu_k
                S_k = np.einsum("t,ti,tj->ij", gw[:, k], diff, diff) / gw_sum
                c_init_k = g_covs[k] if g_covs[k].ndim == 2 else np.diag(g_covs[k])
                S_blend = 0.35 * S_k + 0.65 * c_init_k
                if self.covariance_type != "full":
                    S_blend = np.diag(np.diag(S_blend))
                self._covars_[k] = 0.5 * (S_blend + S_blend.T) + 1e-3 * np.eye(d)

                if self.estimate_nu and g_sum > 15.0:
                    w_k = w[:, k]
                    log_w_k = digamma(0.5 * (self.dof_[k] + d)) - np.log(0.5 * (self.dof_[k] + D2[:, k]))
                    avg_term = float(np.sum(gamma[:, k] * (log_w_k - w_k)) / g_sum)

                    def neg_q_nu(nu_val: float) -> float:
                        half_nu = 0.5 * nu_val
                        return -(half_nu * np.log(half_nu) - gammaln(half_nu) + half_nu * avg_term)

                    opt = minimize_scalar(neg_q_nu, bounds=self.nu_bounds, method="bounded")
                    if opt.success:
                        self.dof_[k] = float(np.clip(opt.x, self.nu_bounds[0], self.nu_bounds[1]))

            if abs(ll - prev_ll) < self.tol:
                break
            prev_ll = ll

        # Rescale means and scale matrices back to raw feature units
        self.means_ = self.means_ * sd_global[None, :] + mu_global[None, :]
        scale_mat = np.outer(sd_global, sd_global)
        for k in range(K):
            self._covars_[k] = self._covars_[k] * scale_mat

        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Full-sample forward-backward posterior probabilities P(s_t = k | X_{1:T})."""
        X_arr = np.asarray(X, dtype=float)
        _, gamma, _, _ = self._forward_backward(X_arr)
        return gamma

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Most probable state sequence from full-sample smoother."""
        return np.argmax(self.predict_proba(X), axis=1).astype(int)

    def score(self, X: np.ndarray) -> float:
        """Total log-likelihood ln P(X_{1:T})."""
        X_arr = np.asarray(X, dtype=float)
        ll, _, _, _ = self._forward_backward(X_arr)
        return ll


def fit_student_t_hmm(
    X: np.ndarray,
    n_states: int = 3,
    covariance_type: str = "full",
    df_nu: float = 5.0,
    estimate_nu: bool = False,
    nu_bounds: tuple[float, float] = (3.5, 25.0),
    n_iter: int = 20,
    tol: float = 1e-2,
    random_state: int = 42,
) -> StudentTHMM:
    """
    Fit a Multivariate Student-t HMM on 2D feature array `X = [log_return, rolling_vol]`
    and sort states by ascending volatility (0 = calmest, K-1 = most volatile).
    """
    X_arr = np.asarray(X, dtype=float)
    if X_arr.ndim != 2 or X_arr.shape[1] < 2:
        raise ValueError("X must be a 2D array with at least 2 columns [log_return, rolling_vol].")
    if len(X_arr) < n_states * 5:
        raise ValueError(f"Need at least {n_states * 5} observations to fit a {n_states}-state HMM.")

    model = StudentTHMM(
        n_components=n_states,
        covariance_type=covariance_type,
        df_nu=df_nu,
        estimate_nu=estimate_nu,
        nu_bounds=nu_bounds,
        n_iter=n_iter,
        tol=tol,
        random_state=random_state,
    )
    model.fit(X_arr)
    sort_hmm_states_by_volatility(model)
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
    distribution: str = "gaussian",
    df_nu: float = 5.0,
    estimate_nu: bool = False,
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

    dist_clean = str(distribution).strip().lower()

    def _fit_fn(X_sub: np.ndarray):
        if dist_clean in ("student_t", "student-t", "t"):
            return fit_student_t_hmm(
                X_sub,
                n_states=n_states,
                covariance_type=covariance_type,
                df_nu=df_nu,
                estimate_nu=estimate_nu,
                random_state=random_state,
            )
        return fit_gaussian_hmm(
            X_sub,
            n_states=n_states,
            covariance_type=covariance_type,
            random_state=random_state,
        )

    # 1. Full-sample fit (sorted deterministically by vol)
    full_model = _fit_fn(X_arr)
    fwd_proba = forward_filter_proba(full_model, X_arr)
    smooth_proba = full_model.predict_proba(X_arr)
    vit_states = full_model.predict(X_arr)

    # 2. Expanding-window walk-forward refit + forward filter
    wf_proba = np.zeros((n_samples, n_states), dtype=float)
    if eff_min_train >= n_samples:
        wf_proba[:] = fwd_proba
    else:
        init_model = _fit_fn(X_arr[:eff_min_train])
        wf_proba[:eff_min_train] = forward_filter_proba(init_model, X_arr[:eff_min_train])

        for start in range(eff_min_train, n_samples, eff_step):
            end = min(start + eff_step, n_samples)
            step_model = _fit_fn(X_arr[:start])
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


def compute_switching_stats(states: np.ndarray, start: int = 0) -> dict[str, float]:
    """
    Summarize how "jumpy" a causal regime sequence is, measured from index `start` onward.

    Returns:
      - ``switches``: number of day-over-day regime changes
      - ``switches_per_year``: changes per 252 trading days
      - ``whipsaws``: regime spells lasting only 1-2 days that are both entered and exited
        (i.e. short flips sandwiched between two other spells)
      - ``whipsaws_per_year``: the same, per 252 trading days
      - ``avg_spell_days``: average length of a regime spell in trading days
    """
    s = np.asarray(states)[int(start):]
    n = len(s)
    if n < 2:
        return {
            "switches": 0.0,
            "switches_per_year": 0.0,
            "whipsaws": 0.0,
            "whipsaws_per_year": 0.0,
            "avg_spell_days": float(n),
        }
    change_idx = np.flatnonzero(s[1:] != s[:-1]) + 1
    bounds = np.concatenate(([0], change_idx, [n]))
    spell_lengths = np.diff(bounds)
    # Interior spells only: a whipsaw must be entered AND exited inside the window.
    interior = spell_lengths[1:-1] if len(spell_lengths) > 2 else np.array([], dtype=int)
    whipsaws = int(np.sum(interior <= 2))
    years = n / 252.0
    return {
        "switches": float(len(change_idx)),
        "switches_per_year": float(len(change_idx) / years),
        "whipsaws": float(whipsaws),
        "whipsaws_per_year": float(whipsaws / years),
        "avg_spell_days": float(np.mean(spell_lengths)),
    }
