import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from explorer import ASSET_CLASSES, apply_filters, cascade, options_for, search, top_counts, treemap_frame  # noqa: E402


@pytest.fixture
def eq():
    return pd.DataFrame({
        "symbol": ["NVDA", "AMD", "TSM", "ASML", "SAP", "JPM", "XYZ"],
        "name": ["NVIDIA Corporation", "Advanced Micro Devices", "Taiwan Semiconductor", "ASML Holding",
                 "SAP SE", "JPMorgan Chase", None],
        "summary": ["Designs GPUs and semiconductor chips", "Semiconductor company making CPUs",
                    "Contract chip foundry", "Lithography machines for semiconductor makers",
                    "Enterprise software", "Investment bank", ""],
        "country": ["United States", "United States", "Taiwan", "Netherlands", "Germany", "United States", None],
        "sector": ["Information Technology"] * 5 + ["Financials", None],
        "industry_group": ["Semiconductors"] * 4 + ["Software & Services", "Banking", None],
        "industry": ["Semis"] * 4 + ["Software", "Banks", None],
        "exchange": ["NMS", "NMS", "TAI", "AMS", "GER", "NYQ", "NYQ"],
        "market_cap": ["Mega Cap", "Large Cap", "Mega Cap", "Mega Cap", "Large Cap", "Mega Cap", "Nano Cap"],
    })


def test_options_sorted_and_market_cap_in_size_order(eq):
    assert options_for(eq, "country") == ["Germany", "Netherlands", "Taiwan", "United States"]
    assert options_for(eq, "market_cap") == ["Mega Cap", "Large Cap", "Nano Cap"]
    assert options_for(eq, "missing_column") == []


def test_apply_filters_empty_selection_is_noop(eq):
    assert len(apply_filters(eq, {"country": [], "sector": []})) == len(eq)
    out = apply_filters(eq, {"country": ["United States"], "market_cap": ["Mega Cap"]})
    assert set(out["symbol"]) == {"NVDA", "JPM"}


def test_cascade_narrows_downstream_options(eq):
    order = ["country", "sector", "industry_group"]
    out, opts, cleaned = cascade(eq, order, {"country": ["United States"]})
    assert set(out["symbol"]) == {"NVDA", "AMD", "JPM"}  # XYZ has no country
    assert opts["sector"] == ["Financials", "Information Technology"]
    assert "Software & Services" not in opts["industry_group"]  # SAP is German


def test_cascade_drops_stale_downstream_selection(eq):
    order = ["country", "industry_group"]
    out, opts, cleaned = cascade(eq, order, {"country": ["Germany"], "industry_group": ["Semiconductors"]})
    assert cleaned["industry_group"] == []  # no German semis -> selection dropped, not an empty result
    assert list(out["symbol"]) == ["SAP"]


def test_search_exact_substring_fuzzy_and_summary(eq):
    assert search(eq, "nvda").iloc[0]["symbol"] == "NVDA"
    assert search(eq, "nvda").iloc[0]["match"] == 100
    assert "JPM" in set(search(eq, "chase")["symbol"])
    assert "TSM" in set(search(eq, "taiwan semiconducter")["symbol"])  # typo tolerated
    typo = search(eq, "semiconducter")  # summary words typo-corrected -> NVDA, AMD, ASML via summary
    assert {"NVDA", "AMD", "ASML", "TSM"} <= set(typo["symbol"])
    hits = set(search(eq, "lithography machines")["symbol"])
    assert hits == {"ASML"}
    assert search(eq, "").equals(eq)
    assert search(eq, "zzzzqqq").empty


def test_treemap_and_counts_handle_missing(eq):
    tree = treemap_frame(eq, ["sector", "industry_group"])
    assert tree["count"].sum() == len(eq)
    assert "Unclassified" in set(tree["sector"])
    top = top_counts(eq, "country", n=2)
    assert len(top) == 2
    assert top.iloc[0]["country"] == "United States" and top.iloc[0]["count"] == 3


def test_every_class_config_is_consistent():
    for spec in ASSET_CLASSES.values():
        assert spec.filters and spec.tree and spec.bar
        assert set(spec.tree) <= set(spec.filters) | {"currency"}


@pytest.mark.network
def test_real_equities_options_match_library():
    """Our unfiltered option lists equal the library's own show_options (needs the cached data)."""
    fd = pytest.importorskip("financedatabase")
    try:
        lib = fd.Equities().show_options()
        from data import load_class
        df = load_class("Equities")
    except Exception as error:  # offline and no cache
        pytest.skip(f"FinanceDatabase data unavailable: {error}")
    for col in ["country", "sector", "industry_group", "industry"]:
        assert options_for(df, col) == sorted(str(v) for v in lib[col])
