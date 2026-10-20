"""Pure filter / search / aggregation logic for the FinanceDatabase explorer (no Streamlit)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

WORD = re.compile(r"[a-z][a-z0-9&\-]{2,}")
MARKET_CAP_ORDER = ["Mega Cap", "Large Cap", "Mid Cap", "Small Cap", "Micro Cap", "Nano Cap"]


@dataclass(frozen=True)
class AssetClass:
    label: str
    loader: str  # attribute name on the financedatabase module
    filters: list[str]  # cascade order; each must be a column
    tree: list[str]  # treemap hierarchy
    bar: str  # column for the bar chart
    columns: list[str] = field(default_factory=list)  # table columns (after symbol)


ASSET_CLASSES: dict[str, AssetClass] = {
    "Equities": AssetClass(
        "Equities", "Equities",
        ["country", "sector", "industry_group", "industry", "exchange", "market_cap"],
        ["sector", "industry_group", "industry"], "country",
        ["name", "country", "sector", "industry_group", "industry", "exchange", "market_cap", "currency"],
    ),
    "ETFs": AssetClass(
        "ETFs", "ETFs",
        ["category_group", "category", "family", "exchange", "currency"],
        ["category_group", "category"], "exchange",
        ["name", "category_group", "category", "family", "exchange", "currency"],
    ),
    "Funds": AssetClass(
        "Funds", "Funds",
        ["category_group", "category", "family", "exchange", "currency"],
        ["category_group", "category"], "exchange",
        ["name", "category_group", "category", "family", "exchange", "currency"],
    ),
    "Indices": AssetClass(
        "Indices", "Indices",
        ["category_group", "category", "exchange", "currency"],
        ["category_group", "category"], "exchange",
        ["name", "category_group", "category", "exchange", "currency"],
    ),
    "Cryptos": AssetClass(
        "Cryptos", "Cryptos",
        ["cryptocurrency", "currency", "exchange"],
        ["currency", "cryptocurrency"], "currency",
        ["name", "cryptocurrency", "currency", "exchange"],
    ),
    "Currencies": AssetClass(
        "Currencies", "Currencies",
        ["base_currency", "quote_currency", "exchange"],
        ["base_currency", "quote_currency"], "base_currency",
        ["name", "base_currency", "quote_currency", "exchange"],
    ),
    "Money Markets": AssetClass(
        "Money Markets", "Moneymarkets",
        ["family", "currency", "exchange"],
        ["family"], "currency",
        ["name", "family", "currency", "exchange"],
    ),
}

PRETTY = {
    "industry_group": "Industry group",
    "market_cap": "Market cap",
    "category_group": "Category group",
    "base_currency": "Base currency",
    "quote_currency": "Quote currency",
    "cryptocurrency": "Crypto",
}


def pretty(col: str) -> str:
    return PRETTY.get(col, col.replace("_", " ").capitalize())


def options_for(df: pd.DataFrame, column: str) -> list[str]:
    """Sorted non-empty values of a column (market-cap bands in size order)."""
    if column not in df.columns:
        return []
    values = df[column].dropna().astype(str)
    values = sorted(v for v in values.unique() if v.strip())
    if column == "market_cap":
        values = [v for v in MARKET_CAP_ORDER if v in values] + [v for v in values if v not in MARKET_CAP_ORDER]
    return values


def apply_filters(df: pd.DataFrame, selections: dict[str, list[str]]) -> pd.DataFrame:
    """Keep rows whose column is in the chosen values. Empty/missing selection = no filter."""
    mask = pd.Series(True, index=df.index)
    for column, chosen in selections.items():
        if chosen and column in df.columns:
            mask &= df[column].astype(str).isin([str(c) for c in chosen])
    return df[mask]


def cascade(df: pd.DataFrame, order: list[str], selections: dict[str, list[str]]):
    """Walk the filters in order. Returns (filtered_df, options_per_column, cleaned_selections).

    Each column's options come from rows that pass every filter *above* it, and a selected
    value that is no longer available is dropped (so the cascade never dead-ends).
    """
    current = df
    options: dict[str, list[str]] = {}
    cleaned: dict[str, list[str]] = {}
    for column in order:
        opts = options_for(current, column)
        options[column] = opts
        chosen = [v for v in selections.get(column, []) if v in opts]
        cleaned[column] = chosen
        if chosen:
            current = apply_filters(current, {column: chosen})
    return current, options, cleaned


def search(df: pd.DataFrame, query: str, threshold: int = 80, limit: int | None = None) -> pd.DataFrame:
    """Rank rows by how well they match the query.

    - exact symbol match: 100; symbol/name substring: 95
    - fuzzy name match (RapidFuzz WRatio, typo tolerant): its score if >= threshold
    - every query word appears in the summary: 85 (80 when a word was typo-corrected
      against the summaries' own vocabulary)
    Returns matching rows sorted by score (column ``match``), best first.
    """
    query = (query or "").strip()
    if not query or df.empty:
        return df
    from rapidfuzz import fuzz, process

    q = query.lower()
    symbol = df["symbol"].astype(str).str.lower()
    name = df["name"].fillna("").astype(str) if "name" in df.columns else pd.Series("", index=df.index)
    summary = df["summary"].fillna("").astype(str).str.lower() if "summary" in df.columns else pd.Series("", index=df.index)

    score = pd.Series(0.0, index=df.index)
    lname = name.str.lower()
    score[symbol == q] = 100
    sub = symbol.str.contains(q, regex=False) | lname.str.contains(q, regex=False)
    score[sub & (score < 95)] = 95

    if len(q) >= 3:
        fuzzy = process.cdist([q], lname.tolist(), scorer=fuzz.WRatio, processor=None, workers=-1)[0]
        fuzzy = pd.Series(fuzzy, index=df.index)
        fuzzy[fuzzy < threshold] = 0
        score = score.where(score >= fuzzy, fuzzy)

    words = [w for w in q.split() if w]
    in_summary = pd.Series(True, index=df.index)
    corrected = False
    vocab: list[str] | None = None
    for w in words:
        hits = summary.str.contains(w, regex=False)
        if not hits.any() and len(w) >= 4:
            # typo in the summary search: swap the word for close words that do occur (e.g. semiconductr -> semiconductor)
            if vocab is None:
                vocab = sorted({t for text in summary for t in WORD.findall(text)})
            close = [m for m, _s, _i in process.extract(w, vocab, scorer=fuzz.ratio, limit=3, score_cutoff=85)]
            if close:
                corrected = True
                hits = summary.str.contains("|".join(re.escape(c) for c in close), regex=True)
        in_summary &= hits
    summary_score = 80 if corrected else 85
    score[in_summary & (score < summary_score)] = summary_score

    out = df.assign(match=score.round(0))
    out = out[out["match"] > 0].sort_values(["match", "symbol"], ascending=[False, True])
    return out.head(limit) if limit else out


def treemap_frame(df: pd.DataFrame, path: list[str]) -> pd.DataFrame:
    """Counts per leaf of the hierarchy, with missing levels labelled 'Unclassified'."""
    cols = [c for c in path if c in df.columns]
    if not cols or df.empty:
        return pd.DataFrame(columns=cols + ["count"])
    tmp = df[cols].astype("object").fillna("Unclassified").astype(str)
    tmp = tmp.replace("", "Unclassified")
    return tmp.groupby(cols, dropna=False).size().reset_index(name="count")


def top_counts(df: pd.DataFrame, column: str, n: int = 15) -> pd.DataFrame:
    if column not in df.columns or df.empty:
        return pd.DataFrame(columns=[column, "count"])
    counts = df[column].dropna().astype(str).value_counts().head(n)
    return counts.rename_axis(column).reset_index(name="count")
