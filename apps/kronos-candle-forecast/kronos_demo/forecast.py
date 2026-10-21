"""Load Kronos from Hugging Face and sample several forecast paths on CPU."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .data import KRONOS_COLS

VENDOR = Path(__file__).resolve().parent.parent / "kronos_vendor"

# name -> (model repo, tokenizer repo, max context, params)
MODELS = {
    "Kronos-mini": ("NeoQuasar/Kronos-mini", "NeoQuasar/Kronos-Tokenizer-2k", 2048, "4.1M"),
    "Kronos-small": ("NeoQuasar/Kronos-small", "NeoQuasar/Kronos-Tokenizer-base", 512, "24.7M"),
    "Kronos-base": ("NeoQuasar/Kronos-base", "NeoQuasar/Kronos-Tokenizer-base", 512, "102.3M"),
}
DEFAULT_MODEL = "Kronos-small"


def _import_upstream():
    """Import the vendored upstream `model` package (MIT, shiyu-coder/Kronos)."""
    if str(VENDOR) not in sys.path:
        sys.path.insert(0, str(VENDOR))
    from model import Kronos, KronosPredictor, KronosTokenizer  # noqa: E402

    return Kronos, KronosTokenizer, KronosPredictor


def load_predictor(name: str = DEFAULT_MODEL, device: str = "cpu"):
    """Download (first run only) and build a KronosPredictor. Cache this in the app."""
    import torch

    Kronos, KronosTokenizer, KronosPredictor = _import_upstream()
    model_id, tok_id, max_ctx, _ = MODELS[name]
    torch.set_grad_enabled(False)
    tokenizer = KronosTokenizer.from_pretrained(tok_id)
    model = Kronos.from_pretrained(model_id)
    tokenizer.eval()
    model.eval()
    return KronosPredictor(model, tokenizer, device=device, max_context=max_ctx)


@dataclass
class Forecast:
    timestamps: pd.Series      # future candle stamps (len N)
    paths: np.ndarray          # (K, N, 6) in KRONOS_COLS order
    median: pd.DataFrame       # N x KRONOS_COLS, median candle per step
    q: dict                    # {10: close array, 25: ..., 75: ..., 90: ...}


def summarise_paths(paths: np.ndarray, timestamps: pd.Series) -> Forecast:
    """Median candle + close quantiles across the sampled paths."""
    paths = np.asarray(paths, dtype="float64")
    med = np.median(paths, axis=0)
    median = pd.DataFrame(med, columns=KRONOS_COLS)
    # keep each median candle self-consistent (high >= body >= low)
    body_hi = median[["open", "close"]].max(axis=1)
    body_lo = median[["open", "close"]].min(axis=1)
    median["high"] = np.maximum(median["high"], body_hi)
    median["low"] = np.minimum(median["low"], body_lo)
    median.insert(0, "timestamps", pd.DatetimeIndex(timestamps))
    close = paths[:, :, KRONOS_COLS.index("close")]
    q = {p: np.percentile(close, p, axis=0) for p in (10, 25, 75, 90)}
    return Forecast(pd.Series(pd.DatetimeIndex(timestamps)), paths, median, q)


def sample_paths(predictor, context: pd.DataFrame, future_ts: pd.Series, n_paths: int = 20,
                 T: float = 1.0, top_p: float = 0.9, seed: int = 42) -> Forecast:
    """Run Kronos on `context` (timestamps + KRONOS_COLS) and keep every path.

    Upstream `predict(sample_count=K)` averages the K samples internally, so instead we
    feed the same series K times to `predict_batch(sample_count=1)`: one independent
    sampled path per batch row, in a single batched pass.
    """
    import torch

    torch.manual_seed(int(seed))
    np.random.seed(int(seed))
    x_df = context[KRONOS_COLS].reset_index(drop=True)
    x_ts = pd.Series(pd.DatetimeIndex(context["timestamps"]))
    y_ts = pd.Series(pd.DatetimeIndex(future_ts))
    k = max(1, int(n_paths))
    outs = predictor.predict_batch(
        df_list=[x_df] * k,
        x_timestamp_list=[x_ts] * k,
        y_timestamp_list=[y_ts] * k,
        pred_len=len(y_ts),
        T=float(T),
        top_k=0,
        top_p=float(top_p),
        sample_count=1,
        verbose=False,
    )
    paths = np.stack([o[KRONOS_COLS].to_numpy() for o in outs], axis=0)
    return summarise_paths(paths, y_ts)
