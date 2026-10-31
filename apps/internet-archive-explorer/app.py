"""Internet Archive Explorer: free films, 78s and live concerts, with a commercial-reuse flag."""
from __future__ import annotations

import html
import re
import time
from pathlib import Path

import requests
import streamlit as st

from iaexplorer.client import (COLLECTIONS, LICENSE_FILTERS, MEDIA_TYPES, SORTS, USER_AGENT, IAClient,
                               build_query, make_session)
from iaexplorer.media import (best_audio_tracks, details_url, display_collections, doc_to_row, doc_year,
                              docs_to_frame, download_url, downloadable_files, first, human_size,
                              playable_files, thumbnail_url, to_csv_bytes)
from iaexplorer.rights import classify

st.set_page_config(page_title="Internet Archive Explorer", page_icon="🎞️", layout="wide")

HERE = Path(__file__).parent
MAX_INLINE_DOWNLOAD = 200 * 1024 * 1024  # larger files open on archive.org instead
EXPORT_MAX = 500


@st.cache_resource
def get_client() -> IAClient:
    return IAClient(make_session(str(HERE / ".ia_cache")), min_interval=1.0)


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def cached_search(query: str, rows: int, page: int, sort: str | None):
    r = get_client().search(query, rows=rows, page=page, sort=sort)
    return r.num_found, r.docs


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def cached_metadata(identifier: str) -> dict:
    return get_client().metadata(identifier)


def strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>|</p>", "\n", str(text or ""), flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def fetch_bytes(url: str):
    """Deferred download: runs only when the user clicks. Retries the Archive's occasional 5xx."""
    def _get() -> bytes:
        last = None
        for attempt in range(3):
            try:
                r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=180)
                if r.status_code < 500:
                    r.raise_for_status()
                    return r.content
                last = requests.HTTPError(f"{r.status_code} from archive.org")
            except requests.ConnectionError as e:
                last = e
            time.sleep(2 * (attempt + 1))
        raise last
    return _get


def badge(verdict) -> str:
    if verdict.commercial_ok:
        return f":green-background[✅ Commercial reuse OK · {verdict.label}]"
    return f":orange-background[⚠️ Flagged · {verdict.label}]"


# ---------------------------------------------------------------- sidebar
st.sidebar.title("🎞️ Search the Archive")
with st.sidebar.form("search"):
    source = st.selectbox("Collection", list(COLLECTIONS), index=0)
    text = st.text_input("Search words (optional)", placeholder='e.g. "mount shasta", train, jazz, 1950s kitchen')
    preset_mt = COLLECTIONS[source]["mediatype"]
    mt_labels = list(MEDIA_TYPES)
    mt_default = next((i for i, k in enumerate(mt_labels) if MEDIA_TYPES[k] == preset_mt), 0)
    media_label = st.selectbox("Media type", mt_labels, index=mt_default,
                               help="Defaults to the collection's own type. 'Any' searches everything.")
    use_years = st.checkbox("Filter by year", value=False,
                            help="Items without a year are left out when this is on.")
    years = st.slider("Year range", 1890, 2026, (1930, 1970), disabled=False)
    license_filter = st.radio("License / rights", LICENSE_FILTERS, index=0)
    sort_label = st.selectbox("Sort", list(SORTS), index=0)
    rows = st.select_slider("Results per page", [12, 24, 48], value=24)
    page = st.number_input("Page", min_value=1, max_value=400, value=1, step=1)
    submitted = st.form_submit_button("Search", type="primary", width="stretch")

st.sidebar.caption(
    "Commercial reuse **OK** = public domain, CC0, CC-BY or CC-BY-SA declared on the item. "
    "NC, ND, other licenses and **no declared license** are flagged. Screening aid, not legal advice."
)
st.sidebar.caption(f"Polite mode: 1 live request/second max, 24 h cache. Live requests this session: "
                   f"{get_client().live_requests}")

collection = COLLECTIONS[source]["collection"]
if collection is None and not text.strip():
    st.sidebar.info("Free-text mode: type some search words.")

query = build_query(
    collection=collection, text=text,
    year_from=years[0] if use_years else None, year_to=years[1] if use_years else None,
    mediatype=MEDIA_TYPES[media_label], license_filter=license_filter,
)

# ---------------------------------------------------------------- header
st.title("Internet Archive Explorer")
st.caption("Free, keyless search of archive.org films, 78rpm records and live concerts: preview, download, "
           "and check commercial reuse before it goes in a video or product.")

if collection is None and not text.strip():
    st.stop()

try:
    with st.spinner("Searching archive.org…"):
        num_found, docs = cached_search(query, int(rows), int(page), SORTS[sort_label])
except requests.RequestException as e:
    st.error(f"archive.org didn't answer ({e}). Try again in a minute; results are cached once they load.")
    st.stop()

ok_count = sum(classify(d.get("licenseurl"), d.get("rights")).commercial_ok for d in docs)
c1, c2, c3 = st.columns(3)
c1.metric("Matches on archive.org", f"{num_found:,}")
c2.metric("Commercial reuse OK (this page)", f"{ok_count} / {len(docs)}")
c3.metric("Flagged (this page)", f"{len(docs) - ok_count}")
with st.expander("Query sent to archive.org"):
    st.code(query, language="text")

# ---------------------------------------------------------------- item detail
sel = st.session_state.get("selected")


def show_item(identifier: str):
    try:
        with st.spinner("Loading item…"):
            data = cached_metadata(identifier)
    except (requests.RequestException, LookupError) as e:
        st.error(f"Couldn't load {identifier}: {e}")
        return
    md = data.get("metadata", {})
    files = data.get("files", [])
    verdict = classify(md.get("licenseurl"), md.get("rights"))
    colls = display_collections(md.get("collection"))
    stream_only = "stream_only" in colls.split("; ")

    with st.container(border=True):
        top = st.columns([5, 1])
        top[0].subheader(str(first(md.get("title")) or identifier))
        if top[1].button("✕ Close", key="close"):
            st.session_state.pop("selected", None)
            st.rerun()
        left, right = st.columns([1, 2])
        with left:
            st.image(thumbnail_url(identifier), width="stretch")
            st.markdown(badge(verdict))
            st.caption(verdict.reason)
            if md.get("licenseurl"):
                st.markdown(f"License: [{first(md['licenseurl'])}]({first(md['licenseurl'])})")
            facts = {
                "Year": doc_year(md) or "?", "Creator": first(md.get("creator")) or "?",
                "Collection": colls or "?", "Identifier": identifier,
            }
            for k, v in facts.items():
                st.markdown(f"**{k}:** {v}")
            st.link_button("Open on archive.org ↗", details_url(identifier))
            if md.get("rights"):
                with st.expander("Rights statement"):
                    st.write(strip_html(" ".join(md["rights"]) if isinstance(md["rights"], list) else md["rights"]))
            if md.get("description"):
                with st.expander("Description"):
                    d = md["description"]
                    st.write(strip_html(" ".join(d) if isinstance(d, list) else d)[:4000])
        with right:
            play = playable_files(files)
            tracks = best_audio_tracks(files)
            if play["video"]:
                names = [f["name"] for f in play["video"]]
                pick = st.selectbox("Video file", names, index=0, key=f"v-{identifier}")
                st.video(download_url(identifier, pick))
            elif tracks:
                names = [f["name"] for f in tracks]
                labels = {f["name"]: (f.get("title") or f["name"]) for f in tracks}
                pick = st.selectbox(f"Track ({len(names)})", names, index=0, key=f"a-{identifier}",
                                    format_func=lambda n: labels[n])
                st.audio(download_url(identifier, pick))
            else:
                st.info("No browser-playable video or audio on this item.")

            st.markdown("**Download files**")
            if stream_only:
                st.warning("This item is **stream only**: the Archive doesn't allow downloads.")
            else:
                dl = downloadable_files(files)[:30]
                if not dl:
                    st.caption("No downloadable media files.")
                for i, f in enumerate(dl):
                    size = int(f.get("size") or 0)
                    row = st.columns([4, 2, 1, 2])
                    row[0].markdown(f"`{f['name']}`")
                    row[1].caption(f"{f.get('format', '?')} · {f.get('source', '')}")
                    row[2].caption(human_size(size))
                    url = download_url(identifier, f["name"])
                    if 0 < size <= MAX_INLINE_DOWNLOAD:
                        row[3].download_button("⬇ Download", data=fetch_bytes(url),
                                               file_name=Path(f["name"]).name, key=f"dl-{identifier}-{i}",
                                               on_click="ignore", width="stretch")
                    else:
                        row[3].link_button("Open ↗", url, width="stretch")
            if not verdict.commercial_ok:
                st.caption("⚠️ Flagged items may still be usable (e.g. old US recordings now public domain), "
                           "but check the rights yourself before commercial use.")


if sel:
    show_item(sel)

# ---------------------------------------------------------------- results
tab_grid, tab_table = st.tabs(["🖼️ Results", "📄 Table & CSV"])

with tab_grid:
    if not docs:
        st.info("No matches. Widen the year range, switch the license filter to All, or change the words.")
    cols_per_row = 4
    for start in range(0, len(docs), cols_per_row):
        cols = st.columns(cols_per_row)
        for col, d in zip(cols, docs[start:start + cols_per_row]):
            row = doc_to_row(d)
            v = classify(d.get("licenseurl"), d.get("rights"))
            with col.container(border=True):
                st.image(thumbnail_url(row["identifier"]), width="stretch")
                st.markdown(f"**{row['title'][:80]}**")
                meta = " · ".join(str(x) for x in [row["year"] or "year ?", row["mediatype"]] if x)
                st.caption(meta)
                st.markdown(badge(v))
                if st.button("▶ Preview & download", key=f"open-{row['identifier']}", width="stretch"):
                    st.session_state["selected"] = row["identifier"]
                    st.rerun()

with tab_table:
    df = docs_to_frame(docs)
    st.dataframe(df, width="stretch", hide_index=True,
                 column_order=["commercial_ok", "title", "year", "license", "mediatype", "collection",
                               "identifier", "license_url", "rights", "source_url"],
                 column_config={"source_url": st.column_config.LinkColumn("source_url"),
                                "license_url": st.column_config.LinkColumn("license_url")})
    a, b = st.columns(2)
    a.download_button("⬇ CSV of this page", data=to_csv_bytes(docs), file_name="internet-archive-page.csv",
                      mime="text/csv", width="stretch")
    n_export = min(num_found, EXPORT_MAX)
    if b.button(f"Fetch top {n_export} results for CSV (1 request)", width="stretch",
                disabled=num_found == 0):
        with st.spinner("Fetching…"):
            _, big = cached_search(query, EXPORT_MAX, 1, SORTS[sort_label])
        st.session_state["export"] = (query, to_csv_bytes(big), len(big))
    exp = st.session_state.get("export")
    if exp and exp[0] == query:
        b.download_button(f"⬇ CSV of top {exp[2]} results", data=exp[1], file_name="internet-archive-results.csv",
                          mime="text/csv", width="stretch", type="primary")
