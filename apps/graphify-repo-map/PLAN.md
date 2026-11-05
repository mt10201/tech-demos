# Graphify Repo Map — project plan

## Goal
Make an approachable, local Streamlit explorer that turns a Python codebase into a knowledge graph and a focused, token-saving context bundle.

## Single-user MVP
- Default to the tech-demos repository; also accept a public GitHub repository URL and clone a shallow copy into a temporary directory.
- Index code with Graphify (`graphifyy`) in code-only mode, without an LLM key.
- Show an interactive graph, degree-ranked functions/classes, connected-code communities, and shortest paths between symbols.
- Estimate the tokens in all indexed source versus a focused context bundle of files on the selected path. Clearly label this as an estimate, not measured agent usage.
- Include offline tests, README instructions, screenshots and a short walkthrough video.

## Explicit outs
- No documentation, PDF or image extraction (requires an LLM).
- No private-repository credentials, write access, agent integration, or persistent hosted service.
- No claim that Graphify's token report is a benchmark; token counts are estimates.
- Initial support is constrained by Graphify's own parser coverage and graph model.

## Vertical slices
1. Inspect and adapt to the installed Graphify API; expose a stable local indexing adapter.
2. Add safe GitHub URL parsing/shallow cloning and graph analytics/path tracing.
3. Build the Streamlit interface and downloadable focused context report.
4. Test critical offline logic, run the app, and capture real UI media.

## Stack
- Python 3 + Streamlit: the repository's default, compact interactive UI.
- graphifyy: the technology under evaluation, used locally with no LLM key.
- NetworkX + PyVis: Graphify-compatible graph analytics and clickable HTML visualization.
- tiktoken: reproducible cl100k_base token estimates; optional fallback is documented.
- pytest: critical adapter, graph, path and token tests.

## Folder structure
- `app.py` — Streamlit UI.
- `graphmap/` — Graphify adapter, source loading, analytics, token reports.
- `tests/` — offline critical-logic tests.
- `scripts/capture.py` — real-browser media capture.
- `media/` — screenshots and MP4 walkthrough.
- `requirements.txt`, `README.md`, `PLAN.md`.

## Deferred
Multi-repository comparison, custom graph layout editing, private repos, incremental indexing and live agent token instrumentation.

## Implementation/API notes
Installed and tested `graphifyy==0.9.103`. Its supported local interface is the CLI: `graphify extract PATH --code-only --out OUTPUT`. The resulting graph uses JSON-node-link `links` (not `edges`) and has community IDs on nodes. The app invokes that CLI and normalizes `links`/`edges`; no LLM methods or keys are used. Token savings use cl100k_base estimates and are not represented as measured agent usage.
