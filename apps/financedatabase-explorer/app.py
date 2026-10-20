"""Global Asset Universe Explorer — browse FinanceDatabase's 300k+ symbols in Streamlit."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from data import PRIMARY_LISTING_CLASSES, DataUnavailable, load_class
from explorer import ASSET_CLASSES, cascade, pretty, search, top_counts, treemap_frame

st.set_page_config(page_title="Global Asset Universe Explorer", page_icon="🌐", layout="wide")


@st.cache_data(show_spinner=False, ttl=24 * 3600)
def cached_class(label: str, primary_only: bool):
    return load_class(label, primary_only)  # exceptions are not cached, so Retry works after a failed download


def reset_filters():
    for key in list(st.session_state):
        if key.startswith("f_"):
            st.session_state[key] = []
    st.session_state["query"] = ""


st.title("🌐 Global Asset Universe Explorer")
st.caption(
    "Powered by [FinanceDatabase](https://github.com/JerBouma/FinanceDatabase) — a free, open "
    "catalogue of 300k+ equities, ETFs, funds, indices, cryptos, currencies and money markets. "
    "Classification data only (no prices)."
)

with st.sidebar:
    label = st.radio("Asset class", list(ASSET_CLASSES), key="asset_class", on_change=reset_filters)
    spec = ASSET_CLASSES[label]
    primary_only = st.toggle(
        "Primary listings only", value=True, disabled=label not in PRIMARY_LISTING_CLASSES,
        help="Hide the same security's secondary listings on other exchanges (e.g. Frankfurt, Stuttgart copies "
             "of US stocks). Uses FinanceDatabase's own only_primary_listing option.",
    )

with st.spinner(f"Loading {label}… (first run downloads it from GitHub)"):
    try:
        df = cached_class(label, primary_only and label in PRIMARY_LISTING_CLASSES)
    except DataUnavailable as error:
        st.error(str(error))
        if st.button("Retry download"):
            st.rerun()
        st.stop()

with st.sidebar:
    st.subheader("Filters")
    st.caption("Each list only offers values that still exist after the filters above it.")
    selections = {c: st.session_state.get(f"f_{c}", []) for c in spec.filters}
    filtered, options, cleaned = cascade(df, spec.filters, selections)
    for column in spec.filters:
        key = f"f_{column}"
        if st.session_state.get(key) != cleaned[column]:
            st.session_state[key] = cleaned[column]
        st.multiselect(f"{pretty(column)} ({len(options[column])})", options[column], key=key, placeholder="Any")
    query = st.text_input("Search name / symbol / summary", key="query", placeholder="e.g. semiconductr, NVDA, solar")
    st.button("Clear filters", on_click=reset_filters)

# Re-run the cascade with the widget values from this run (a change above may prune values below).
filtered, options, cleaned = cascade(df, spec.filters, {c: st.session_state.get(f"f_{c}", []) for c in spec.filters})
results = search(filtered, query)

m1, m2, m3 = st.columns(3)
m1.metric(f"{label} in database", f"{len(df):,}")
m2.metric("Matching filters", f"{len(filtered):,}")
m3.metric("Shown (after search)" if query else "Shown", f"{len(results):,}")

if results.empty:
    st.warning("Nothing matches. Loosen a filter or the search.")
    st.stop()

left, right = st.columns([3, 2])
with left:
    tree = treemap_frame(results, spec.tree)
    fig = px.treemap(
        tree, path=[px.Constant(label)] + list(tree.columns[:-1]), values="count",
        color=tree.columns[1] if tree.shape[1] > 2 else tree.columns[0], color_discrete_sequence=px.colors.qualitative.Set3,
    )
    fig.update_traces(textinfo="label+value", root_color="#f4f4f4")
    fig.update_layout(showlegend=False)
    fig.update_layout(margin=dict(t=30, l=0, r=0, b=0), height=460,
                      title=f"Breakdown by {' → '.join(pretty(c) for c in tree.columns[:-1])}")
    st.plotly_chart(fig, width="stretch")
with right:
    bar_col = spec.bar
    if label == "Equities" and len(cleaned.get("country", [])) == 1:
        bar_col = "exchange"  # one country chosen: show its exchanges instead
    counts = top_counts(results, bar_col)
    bar = px.bar(counts, x="count", y=bar_col, orientation="h", text="count")
    bar.update_layout(margin=dict(t=30, l=0, r=0, b=0), height=460, yaxis=dict(autorange="reversed", title=None),
                      title=f"Top {len(counts)} by {pretty(bar_col).lower()}")
    st.plotly_chart(bar, width="stretch")

cols = ["symbol"] + (["match"] if query else []) + [c for c in spec.columns if c in results.columns]
st.subheader(f"Results — {len(results):,} rows")
st.dataframe(results[cols], width="stretch", hide_index=True, height=420)
st.download_button(
    "⬇️ Download CSV", results.drop(columns=["match"], errors="ignore").to_csv(index=False).encode("utf-8"),
    file_name=f"financedatabase_{label.lower().replace(' ', '_')}.csv", mime="text/csv",
)
with st.expander("Peek at summaries of the first 5 results"):
    for _, row in results.head(5).iterrows():
        st.markdown(f"**{row['symbol']} — {row.get('name', '')}**  \n{str(row.get('summary') or '')[:400]}")
