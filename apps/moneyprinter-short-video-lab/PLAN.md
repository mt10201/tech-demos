# MoneyPrinterTurbo Short-Video Lab — project plan

## Goal
Wrap the official MoneyPrinterTurbo CLI in a single-user Streamlit lab that turns a topic or custom script and local/stock media into a downloadable HD short video without publishing it.

## Single-user MVP
- Topic, optional custom script, 9:16 / 16:9 / 1:1 aspect ratio, clip length and sequential media order.
- Official `mpt` CLI execution with Edge TTS, subtitles, no BGM, local uploads or Pexels/Pixabay sources.
- Clear preflight and key gates: pasted script works without an LLM; AI scripting and stock APIs use upstream local config, never secrets entered in this app.
- One task at a time, stage/progress display, safe errors, and playable/downloadable MP4 results retained in local task storage.
- Pre-baked real generated sample, UI screenshots/walkthrough, exact run instructions and critical offline wrapper tests.

## Explicit outs
- No TikTok, Instagram, YouTube or other publishing.
- No API-key collection/storage in the Streamlit UI, no account or cloud integrations.
- No batch jobs, queues, persistent cross-device history, paid AI material providers, or custom Whisper model controls.
- No claim that stock licensing, Edge service availability, or upstream generation is guaranteed.

## Vertical slices
1. Adapt official `mpt` CLI with validated bounded subprocess commands, per-task `MPT_HOME`, JSON/error parsing and result discovery.
2. Save validated local uploads; build an LLM/key/material readiness checklist and safe configuration.
3. Build the Streamlit creation/output UI with live task stages, local playback/download, diagnostics and a pre-baked sample.
4. Generate a real local-material + Edge TTS sample, test offline wrapper logic, and capture real-browser screenshots/video.

## Stack
- Python 3.11+ and Streamlit: repository default, compact single-user creative UI.
- Official MoneyPrinterTurbo `mpt` package: upstream MIT engine, CLI-first integration.
- Standard-library subprocess/json/pathlib: transparent argument-list execution and portable task handling.
- imageio-ffmpeg via MoneyPrinterTurbo: packaged FFmpeg backend; a system FFmpeg can be configured as fallback.
- pytest: critical offline command, configuration and result parsing tests.

## Folder structure
- `app.py` — Streamlit UI.
- `video_lab/` — configuration validation, CLI runner, results and sample helpers.
- `tests/` — offline wrapper/config/result tests.
- `scripts/capture.py` — real-browser media capture.
- `media/` — generated sample, screenshots and walkthrough MP4.
- `requirements.txt`, `README.md`, `PLAN.md`.

## Deferred
Publishing, automated posting schedules, team projects, model/key management UI, custom BGM library, advanced subtitle styling and long-form rendering.
