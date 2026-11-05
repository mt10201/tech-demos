"""Explore a codebase with Graphify's local, code-only knowledge graph."""
from __future__ import annotations

import html
import json
import os
from pathlib import Path
import tempfile

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

from graphmap.core import (GraphifyError, clone_public_repo, communities, extract_graph, github_repo,
                           hubs, path_report, source_files, count_tokens, symbol_path, to_networkx, token_report)

st.set_page_config(page_title="Graphify Repo Map", page_icon="🕸️", layout="wide")
HERE = Path(__file__).parent
DEFAULT_REPO = Path(os.environ.get("GRAPHIFY_DEFAULT_REPO", HERE.parents[1]))

st.title("🕸️ Graphify Repo Map")
st.caption("A local, clickable knowledge graph of your code — no LLM key, no document upload, no agent required.")

with st.sidebar:
    st.header("Index a codebase")
    source = st.radio("Source", ["tech-demos (this repo)", "Public GitHub URL"])
    url = st.text_input("GitHub URL", "https://github.com/Graphify-Labs/graphify",
                        disabled=source.startswith("tech-demos"))
    max_nodes = st.slider("Graph display limit", 50, 1000, 300, 50,
                          help="Analytics use the complete graph. Only the browser view is capped.")
    build = st.button("Build knowledge graph", type="primary", use_container_width=True)
    st.divider()
    st.markdown("**Code-only mode**")
    st.caption("Python AST / tree-sitter extraction runs locally. Docs, PDFs and images are skipped. Public GitHub clones are temporary and shallow.")
    st.link_button("Graphify on GitHub ↗", "https://github.com/Graphify-Labs/graphify")


def make_index(source_root: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="graphify-map-") as temp:
        data = extract_graph(source_root, Path(temp))
    graph = to_networkx(data)
    return {"data": data, "graph": graph, "root": str(source_root),
            "files": source_files(source_root, graph)}


if build:
    try:
        if source.startswith("tech-demos"):
            with st.spinner("Graphify is parsing this repo locally…"):
                st.session_state.index = make_index(DEFAULT_REPO)
                st.session_state.source_name = "mt10201/tech-demos"
        else:
            github_repo(url)
            with tempfile.TemporaryDirectory(prefix="graphify-repo-") as temp:
                with st.spinner("Shallow-cloning and parsing the public repository…"):
                    clone_public_repo(url, Path(temp) / "repo")
                    st.session_state.index = make_index(Path(temp) / "repo")
                    st.session_state.source_name = url
    except (GraphifyError, ValueError, OSError) as exc:
        st.error(str(exc))

index = st.session_state.get("index")
if not index:
    st.info("Choose a repository in the sidebar, then select **Build knowledge graph**.")
    st.markdown("### What you get")
    a, b, c = st.columns(3)
    a.markdown("**1 · See the structure**\n\nClickable symbols and their relationships.")
    b.markdown("**2 · Trace the flow**\n\nFind a shortest connection between two functions.")
    c.markdown("**3 · Focus the context**\n\nEstimate tokens saved versus reading every file.")
    st.stop()

graph = index["graph"]
files = index["files"]
hub_rows = hubs(graph, 100)
community_rows = communities(graph)
local_nodes = [n for n, a in graph.nodes(data=True) if a.get("_callable") and a.get("source_file")]
external_nodes = graph.number_of_nodes() - len(local_nodes)

st.subheader(index.get("source_name", "Codebase"))
m1, m2, m3, m4 = st.columns(4)
m1.metric("Code symbols", f"{len(local_nodes):,}")
m2.metric("Relationships", f"{graph.number_of_edges():,}")
m3.metric("Related-code groups", f"{len(community_rows):,}")
m4.metric("Source files", f"{len(files):,}")

tab_graph, tab_hubs, tab_path, tab_tokens, tab_raw = st.tabs(
    ["🕸️ Graph", "⭐ Hubs & groups", "↝ Path tracer", "🪙 Token report", "{ } Raw graph"])

with tab_graph:
    st.markdown("Drag to explore, scroll to zoom, and click a node for its file and connections.")
    if len(local_nodes) > max_nodes:
        keep = {row["id"] for row in hubs(graph, max_nodes)}
        view = graph.subgraph(keep).copy()
        st.caption(f"Showing the {len(keep):,} most-connected code symbols; external/library nodes hidden. Analytics still use all {graph.number_of_nodes():,} nodes.")
    else:
        view = graph.subgraph(local_nodes).copy()
    net = Network(height="600px", width="100%", directed=True, bgcolor="#0e1117", font_color="#f2f2f2", cdn_resources="remote")
    net.force_atlas_2based(gravity=-45, central_gravity=0.015, spring_length=120)
    for node, attrs in view.nodes(data=True):
        degree = graph.degree(node)
        label = attrs.get("label", node)
        detail = (f"<b>{html.escape(str(label))}</b><br>{html.escape(str(attrs.get('source_file', '')))}"
                  f":{html.escape(str(attrs.get('source_location', '')))}<br>{degree} connections"
                  f"<br>Community {html.escape(str(attrs.get('community', '?')))}")
        net.add_node(node, label=str(label)[:38], title=detail,
                     color="#ffcb6b" if attrs.get("_callable_class") else "#82aaff",
                     size=min(34, 8 + degree * 1.2))
    for start, end, attrs in view.edges(data=True):
        net.add_edge(start, end, title=attrs.get("relation", "related"), color="#596579", arrows="to")
    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", encoding="utf-8", delete=False) as out:
        net.save_graph(out.name)
        graph_html = Path(out.name).read_text(encoding="utf-8")
    components.html(graph_html, height=620, scrolling=False)
    st.caption("Blue = function · amber = class. Hover/click a node for details. External libraries are omitted from this view.")

with tab_hubs:
    st.markdown("### Most-connected functions and classes")
    if hub_rows:
        st.dataframe(pd.DataFrame(hub_rows), hide_index=True, use_container_width=True,
                     column_config={"connections": st.column_config.ProgressColumn("Connections", min_value=0, max_value=max(r["connections"] for r in hub_rows))})
    else:
        st.info("Graphify found no callable code symbols.")
    st.markdown("### Groups of related code")
    st.caption("Communities assigned by Graphify's code-only clustering; labels are numeric because LLM naming is off.")
    for row in community_rows:
        with st.expander(f"Community {row['community']} · {row['symbols']} symbols · {row['files']} files"):
            st.write(row["top_symbols"])

with tab_path:
    st.markdown("### How does one symbol reach another?")
    labels = {n: f"{graph.nodes[n].get('label', n)}  ·  {graph.nodes[n].get('source_file', '')}" for n in local_nodes}
    ordered = sorted(local_nodes, key=lambda n: labels[n])
    if len(ordered) >= 2:
        defaults = [row["id"] for row in hub_rows if row["id"] in labels]
        left, right = st.columns(2)
        start = left.selectbox("From", ordered, index=ordered.index(defaults[0]) if defaults else 0, format_func=labels.get)
        connected_defaults = [n for n in graph.neighbors(defaults[0]) if n in labels] if defaults else []
        default_end = connected_defaults[0] if connected_defaults else (defaults[1] if len(defaults)>1 else ordered[1])
        end = right.selectbox("To", ordered, index=ordered.index(default_end), format_func=labels.get)
        directed_note = st.checkbox("Ignore arrow direction (usually easier to follow across modules)", value=True)
        path = symbol_path(graph, start, end)
        if path:
            st.success(f"Shortest connection: {len(path)-1} hop(s)")
            st.markdown(path_report(graph, path))
            path_files = {graph.nodes[n].get("source_file") for n in path if graph.nodes[n].get("source_file")}
            report = token_report(files, path_files)
            m1, m2, m3 = st.columns(3)
            m1.metric("Full source", f"{report.full_tokens:,} tokens")
            m2.metric("Files on this path", f"{report.focused_tokens:,} tokens")
            m3.metric("Estimated saved", f"{report.reduction_percent:.1f}%")
            context = path_report(graph, path) + "\n\n# Source files\n"
            for name in sorted(path_files):
                if name in files:
                    context += f"\n\n## {name}\n```\n{files[name]}\n```"
            st.download_button("Download focused context (.md)", context, file_name="graphify-focused-context.md")
        else:
            st.warning("No path connects these symbols in the extracted graph. Try a hub in the same community.")
    else:
        st.info("At least two code symbols are needed for path tracing.")

with tab_tokens:
    st.markdown("### Focused context vs reading every file")
    selected_count = st.slider("Files in a focused context bundle", 1, max(1, len(files)), min(5, max(1, len(files))))
    ranked_files = sorted(files, key=lambda name: -sum(1 for n,a in graph.nodes(data=True) if a.get("source_file") == name))
    report = token_report(files, ranked_files[:selected_count])
    a, b, c, d = st.columns(4)
    a.metric("Read every file", f"{report.full_tokens:,}", help=f"{report.full_files} parsed source files")
    b.metric("Focused bundle", f"{report.focused_tokens:,}", help=f"Top {report.focused_files} symbol-dense files")
    c.metric("Estimated tokens saved", f"{report.saved_tokens:,}")
    d.metric("Estimated reduction", f"{report.reduction_percent:.1f}%")
    st.progress(report.reduction_percent / 100)
    st.info("This is a cl100k_base token estimate for a focused file bundle, not a measured agent benchmark. Actual savings depend on the question, retrieval strategy and model tokenizer. Empty/external nodes are not source files.")
    st.dataframe(pd.DataFrame([{"file": name, "estimated_tokens": count_tokens(text)} for name,text in files.items()]).sort_values("estimated_tokens", ascending=False), hide_index=True, use_container_width=True)

with tab_raw:
    st.caption(f"Graphify graph schema: {index['data'].get('graph', {})} · {external_nodes:,} non-local/external nodes omitted from symbol counts.")
    st.download_button("Download graph.json", json.dumps({k:v for k,v in index['data'].items() if not k.startswith('_')}, indent=2), file_name="graph.json", mime="application/json")
    with st.expander("Graphify extraction log"):
        st.code(index['data'].get("_log", ""), language="text")
