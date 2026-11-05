# Agent Reach Explorer — project plan

## Goal
Build a keyless, read-only Streamlit search app that uses Agent Reach to place GitHub repositories, YouTube videos and web results side by side.

## Single-user MVP
- One query searches GitHub, YouTube and the web through the Agent Reach CLI.
- Run the three sources independently so one blocked or unavailable source does not hide the others.
- Normalize JSON results into cards and a table, show source status, and export a combined CSV.
- Clearly gate signed-in Reddit, X and LinkedIn search and speech-to-text YouTube transcripts; never collect credentials.
- Include offline tests, exact installation/run instructions, screenshots and a short walkthrough video.

## Explicit outs
- No login, account-session copying, posting, messaging or credential input.
- No YouTube speech-to-text or transcript workflow in this demo.
- No Reddit, X or signed-in LinkedIn requests.
- No guarantee against upstream bot blocking, HTML/API changes, rate limits or third-party tool breakage.

## Vertical slices
1. Install Agent Reach from its official GitHub release and adapt its CLI JSON output.
2. Add bounded subprocess execution, source normalization and resilient combined-search orchestration.
3. Build the Streamlit interface, status cards, result views, gates and CSV export.
4. Test offline normalization/CLI behavior, run live searches and capture real UI media.

## Stack
- Python 3 + Streamlit: repository default and concise multi-column UI.
- Agent Reach: technology under evaluation, called as a subprocess with JSON output.
- Standard-library `subprocess`, `json` and `csv`: small, inspectable CLI wrapper and export.
- pytest: critical offline wrapper and normalization tests.

## Folder structure
- `app.py` — Streamlit UI.
- `reach/client.py` — Agent Reach CLI adapter, normalization and CSV.
- `tests/` — offline critical-logic tests.
- `scripts/capture.py` — real-browser screenshot/video capture.
- `media/` — screenshots and MP4 walkthrough.
- `requirements.txt`, `README.md`, `PLAN.md`.

## Deferred
Authenticated sources, transcripts, persistent result storage, scheduled searches and custom source plugins.

## Installation/API notes
Agent Reach's README warns that the unrelated PyPI package named `agent-reach` must not be used. Install the official GitHub release archive instead; the app calls `agent-reach <channel> <action> ...` and parses one JSON object with `ok`, `result` and `error`. Installed and live-tested Agent Reach 1.6.1 from the official release ZIP. GitHub uses `gh` with GitHub API fallback, YouTube uses `yt-dlp`, and web uses Exa. Search responses have top-level `items`; useful details are in each item's `raw` object. No setup/login/key was needed. `requirements.txt` pins the official release URL rather than the unrelated PyPI package. The app uses a bounded subprocess adapter and per-source errors.
