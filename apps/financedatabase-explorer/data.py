"""Load one FinanceDatabase asset class as a plain DataFrame (symbol as a column)."""

from __future__ import annotations

import warnings

import pandas as pd

from explorer import ASSET_CLASSES


class DataUnavailable(RuntimeError):
    """The class's data could not be downloaded and there is no local cache yet."""


PRIMARY_LISTING_CLASSES = {"Equities", "ETFs", "Funds"}  # classes whose select() supports only_primary_listing


def load_class(label: str, primary_only: bool = False) -> pd.DataFrame:
    import financedatabase as fd

    spec = ASSET_CLASSES[label]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)  # Funds / Money Markets 'no longer maintained' notice
            kwargs = {"only_primary_listing": True} if primary_only and label in PRIMARY_LISTING_CLASSES else {}
            frame = getattr(fd, spec.loader)().select(**kwargs)
    except Exception as error:  # library raises ValueError wrapping requests errors
        raise DataUnavailable(
            f"Could not load {label} from FinanceDatabase. The first run downloads the data from GitHub "
            f"(raw.githubusercontent.com) and caches it locally; check your internet connection or proxy "
            f"and try again.\n\nDetails: {error}"
        ) from error
    df = pd.DataFrame(frame).reset_index()
    if "symbol" not in df.columns:
        df = df.rename(columns={df.columns[0]: "symbol"})
    df["symbol"] = df["symbol"].astype(str)
    return df
