"""Search GitHub, YouTube and the web side by side with Agent Reach."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import re
import shutil

import streamlit as st

from reach.client import SOURCES, AgentReachClient, SearchResponse, results_csv

st.set_page_config(page_title="Agent Reach Explorer", page_icon="🛰️", layout="wide")
LABELS = {"github": "GitHub", "youtube": "YouTube", "web": "Web"}
ICONS = {"github": "▣", "youtube": "▶", "web": "◎"}


@st.cache_resource
def client() -> AgentReachClient:
    return AgentReachClient()


@st.cache_data(ttl=900, show_spinner=False)
def cached_search(query: str, limit: int) -> dict[str, SearchResponse]:
    # Independent requests keep one blocked source from hiding useful results.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {source: pool.submit(client().search, source, query, limit) for source in SOURCES}
        return {source: future.result() for source, future in futures.items()}


def video_id(url: str) -> str:
    match = re.search(r"(?:[?&]v=|youtu\.be/)([A-Za-z0-9_-]{6,})", url)
    return match.group(1) if match else ""


st.title("🛰️ Agent Reach Explorer")
st.caption("One query. GitHub, YouTube and the web — side by side, keyless and read-only.")

with st.sidebar:
    st.header("Search public sources")
    with st.form("search"):
        query = st.text_input("Query", value="Agent Reach", placeholder="Try: local AI agents")
        limit = st.slider("Results per source", 3, 10, 5)
        submitted = st.form_submit_button("Search all three", type="primary", use_container_width=True)
    st.caption("Searches run concurrently and are cached for 15 minutes.")
    st.divider()
    st.markdown("**Powered by [Agent Reach](https://github.com/Panniantong/Agent-Reach) · MIT**")
    if shutil.which("agent-reach"):
        st.success("Agent Reach CLI found")
    else:
        st.warning("CLI not found — install requirements.txt in the active environment")
    st.caption("This app never asks for a password, session cookie or API key.")

if submitted:
    try:
        with st.spinner("Searching GitHub, YouTube and the web…"):
            st.session_state.responses = cached_search(query, limit)
            st.session_state.query = query
    except Exception as exc:  # defensive UI boundary; client normally returns source errors
        st.error(f"Search could not complete: {exc}")

responses: dict[str, SearchResponse] | None = st.session_state.get("responses")
if not responses:
    st.info("Enter a topic in the sidebar, then select **Search all three**.")
    a, b, c = st.columns(3)
    a.markdown("### ▣ GitHub\nRepositories, descriptions, languages and stars.")
    b.markdown("### ▶ YouTube\nVideos, channels, durations and view counts.")
    c.markdown("### ◎ Web\nPages and readable snippets from semantic web search.")
else:
    st.subheader(f"Results for “{st.session_state.get('query', query)}”")
    metrics = st.columns(3)
    for source, metric in zip(SOURCES, metrics):
        response = responses[source]
        metric.metric(f"{ICONS[source]} {LABELS[source]}", len(response.results),
                      delta=f"{response.elapsed_ms / 1000:.1f}s" if response.elapsed_ms else None,
                      delta_color="off")

    columns = st.columns(3)
    for source, column in zip(SOURCES, columns):
        response = responses[source]
        with column:
            st.markdown(f"## {ICONS[source]} {LABELS[source]}")
            if response.backend:
                st.caption(f"Agent Reach backend: `{response.backend}`")
            if response.error:
                st.error(response.error)
                st.caption("This source failed independently. Try again later or inspect Agent Reach's backend status.")
            elif not response.results:
                st.info("No results returned.")
            for index, result in enumerate(response.results):
                with st.container(border=True):
                    if source == "youtube" and video_id(result.url):
                        st.image(f"https://i.ytimg.com/vi/{video_id(result.url)}/hqdefault.jpg", use_container_width=True)
                    st.markdown(f"**[{result.title}]({result.url})**" if result.url else f"**{result.title}**")
                    byline = " · ".join(part for part in (result.author, result.detail) if part)
                    if byline:
                        st.caption(byline)
                    if result.text:
                        st.write(result.text[:650] + ("…" if len(result.text) > 650 else ""))
                    if result.url:
                        st.link_button(f"Open on {LABELS[source]} ↗", result.url, key=f"open-{source}-{index}", use_container_width=True)

    all_results = [result for response in responses.values() for result in response.results]
    st.divider()
    table_tab, raw_tab = st.tabs(["Table & CSV", "Source diagnostics"])
    with table_tab:
        st.dataframe(
            [{"Source": LABELS[r.source], "Title": r.title, "Author / channel": r.author,
              "Details": r.detail, "URL": r.url} for r in all_results],
            hide_index=True, use_container_width=True,
            column_config={"URL": st.column_config.LinkColumn("URL")},
        )
        st.download_button("Download combined CSV", results_csv(responses.values()),
                           file_name="agent-reach-results.csv", mime="text/csv")
    with raw_tab:
        for source in SOURCES:
            response = responses[source]
            st.markdown(f"**{LABELS[source]}** — {len(response.results)} results · backend `{response.backend or 'unavailable'}`")
            if response.error:
                st.code(response.error, language="text")

st.divider()
st.markdown("### 🔒 Needs session / key — intentionally not enabled")
gates = st.columns(4)
gates[0].markdown("**Reddit**\n\nSigned-in Agent Reach browser session required. This demo sends no Reddit request.")
gates[1].markdown("**X / Twitter**\n\nSigned-in session required; experimental and sensitive to anti-bot changes.")
gates[2].markdown("**LinkedIn**\n\nSigned-in site search gated here. No browser session is copied or accessed.")
gates[3].markdown("**YouTube transcripts**\n\nSpeech-to-text needs a Groq or OpenAI key configured outside this app.")
st.caption("Caveat: public search can break when websites change APIs, markup or bot blocking. Source errors are shown rather than silently replaced.")
