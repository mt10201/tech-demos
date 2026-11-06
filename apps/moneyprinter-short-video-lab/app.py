"""A local-only creative lab for official MoneyPrinterTurbo video generation."""
from __future__ import annotations
from pathlib import Path
import shutil

import streamlit as st

from video_lab.runner import (ASPECTS, MoneyPrinterTurboRunner, VideoRequest,
                              default_home, discover_tasks, inspect_readiness, save_uploads)

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "media" / "sample-generated.mp4"
st.set_page_config(page_title="MoneyPrinterTurbo Short-Video Lab", page_icon="🎬", layout="wide")
st.markdown("""<style>
.block-container{max-width:1240px;padding-top:2.2rem} [data-testid="stHeader"]{background:transparent}
[data-testid="stMetric"]{background:#f4f7f5;border:1px solid #e0e8e2;padding:16px;border-radius:12px}
[data-testid="stSidebar"]{background:#f4f7f5} h1{letter-spacing:-1.8px}
.small-note{font-size:.88rem;color:#53665a}.stDownloadButton button{width:100%}
</style>""", unsafe_allow_html=True)

st.title("🎬 Short-video lab")
st.caption("Topic → narration, visuals & subtitles → HD video. Powered by official MoneyPrinterTurbo.")
st.info("**Local by design.** This demo renders and downloads videos only — it never publishes to TikTok, Instagram or YouTube.")

home = default_home()
ready = inspect_readiness(home)
with st.sidebar:
    st.header("Studio setup")
    st.write("✅ Official `mpt` ready" if ready.mpt_found else "❌ `mpt` not found in this environment")
    st.caption(f"Local workspace: `{home}`")
    st.markdown("**No-key route**")
    st.write("Paste a script + upload images/video. Edge TTS supplies the voiceover without a key.")
    with st.expander("Optional API configuration"):
        st.write(f"LLM script generation: {'configured' if ready.llm_configured else 'not configured'}")
        st.write(f"Pexels: {'key found' if ready.stock_keys['pexels'] else 'free API key needed'}")
        st.write(f"Pixabay: {'key found' if ready.stock_keys['pixabay'] else 'free API key needed'}")
        st.caption("Set keys in MoneyPrinterTurbo's local config.toml using its own WebUI or docs. Never paste them into this lab.")
    st.divider()
    st.caption("Python 3.11+ · FFmpeg via imageio-ffmpeg · Edge subtitle timing by default")

create_tab, sample_tab = st.tabs(["Create a short", "Pre-baked sample"])
with create_tab:
    left, right = st.columns([1.1, .9], gap="large")
    with left:
        st.subheader("1. Tell the story")
        topic = st.text_input("Topic", "A quiet moment beneath Mount Shasta")
        script = st.text_area("Custom script (recommended — no LLM key needed)", height=145,
            value="Leave the noise behind. Look up at the mountain. Take a breath, and make a little room for wonder.",
            help="When this is blank, MoneyPrinterTurbo needs an LLM API key in config.toml.")
        st.subheader("2. Choose the look")
        a, b = st.columns(2)
        aspect = a.radio("Aspect ratio", list(ASPECTS), horizontal=True,
                         format_func=lambda x: f"{x} · {ASPECTS[x][0]}×{ASPECTS[x][1]}")
        voice = b.selectbox("Edge TTS voice", ["en-US-AriaNeural", "en-US-GuyNeural", "en-GB-SoniaNeural", "zh-CN-XiaoxiaoNeural"])
        source = st.radio("Visual materials", ["local", "pexels", "pixabay"], horizontal=True,
                          format_func=lambda x: {"local": "Upload local files", "pexels": "Pexels stock", "pixabay": "Pixabay stock"}[x])
        uploads = None
        if source == "local":
            uploads = st.file_uploader("Images or videos · up to 12 files, 200 MB each",
                                       type=["jpg", "jpeg", "png", "webp", "mp4", "mov", "webm", "avi", "mkv"],
                                       accept_multiple_files=True)
        else:
            st.warning(f"{source.title()} requires its free API key in MoneyPrinterTurbo's local config.toml.")
        clip_duration = st.slider("Maximum seconds per visual", 1, 15, 5)
        can_generate = ready.mpt_found and bool(topic.strip()) and (bool(script.strip()) or ready.llm_configured)
        if not script.strip() and not ready.llm_configured:
            st.warning("Paste a custom script, or configure an LLM for topic-only generation.")
        generate = st.button("Generate HD video", type="primary", disabled=not can_generate, use_container_width=True)
    with right:
        st.subheader("3. Render & review")
        st.markdown("The CLI runs **one task at a time**. Voiceover, subtitles, visual preprocessing and HD encoding can take several minutes.")
        if generate:
            try:
                materials = save_uploads(uploads or [], home / "storage" / "uploads") if source == "local" else ()
                request = VideoRequest(topic, script, aspect, source, materials, voice, clip_duration)
                request.validate()
                progress = st.status("Starting MoneyPrinterTurbo…", expanded=True)
                log_box = progress.empty()
                lines = []
                stages = {"generating audio": "Creating free Edge TTS narration…",
                          "generating subtitle": "Aligning subtitles…",
                          "preprocess local materials": "Preparing local visuals…",
                          "get_video_materials": "Fetching stock visuals…",
                          "combining video": "Assembling the timeline…",
                          "generating video:": "Encoding the final HD video…"}
                def report(line):
                    lines.append(line)
                    low = line.lower()
                    for marker, label in stages.items():
                        if marker in low:
                            progress.update(label=label, state="running", expanded=True)
                    log_box.code("\n".join(lines[-8:]) or "Waiting for task output…", language="text")
                with st.spinner("Rendering — keep this tab open"):
                    result = MoneyPrinterTurboRunner(home).run(request, report)
                progress.update(label="Video ready", state="complete", expanded=False)
                video_path = Path(result.videos[0])
                st.session_state.latest = {"id": result.task_id, "path": str(video_path),
                    "bytes": video_path.read_bytes(), "script": result.script, "aspect": aspect}
            except (ValueError, RuntimeError, OSError) as exc:
                st.error(str(exc))
        latest = st.session_state.get("latest")
        if latest:
            st.success(f"Task complete · `{latest['id']}`")
            st.video(latest["bytes"])
            st.download_button("Download MP4", latest["bytes"], f"short-{latest['id'][:8]}.mp4", "video/mp4", use_container_width=True)
            st.caption(f"{latest['aspect']} · Saved locally at {latest['path']}")
        else:
            st.empty()
            st.markdown("**Output preview**\n\nYour playable MP4 and download button will appear here.")
        with st.expander("Previous local renders"):
            tasks = discover_tasks(home)
            if tasks:
                chosen = st.selectbox("Task", tasks, format_func=lambda t: t["id"])
                st.video(chosen["path"])
            else:
                st.caption("No completed tasks in this lab's workspace yet.")
with sample_tab:
    st.subheader("Real MoneyPrinterTurbo generation")
    st.write("This 8-second, 1080×1920 sample was rendered locally from three generated placeholder images, a pasted script, free Edge TTS and timed subtitles. No LLM or stock API key was used.")
    if SAMPLE.exists():
        col, detail = st.columns([.65, 1])
        col.video(str(SAMPLE))
        detail.download_button("Download sample MP4", SAMPLE.read_bytes(), "moneyprinterturbo-sample.mp4", "video/mp4")
        detail.markdown("**Reproduced settings**\n- Custom English script\n- Local images with subtle zoom\n- `en-US-AriaNeural` voice\n- Edge timestamp subtitles\n- No background music")
    else:
        st.warning("Sample file is missing.")

st.divider()
st.markdown("### Before you render")
cols = st.columns(3)
cols[0].markdown("**Free, not keyless-everything**\n\nCustom scripts, local materials and Edge TTS need no key. AI scripting and stock libraries have separate requirements.")
cols[1].markdown("**Heavy dependencies**\n\nMoneyPrinterTurbo pulls video and speech packages. FFmpeg normally comes through imageio-ffmpeg; Whisper is optional and downloads a model only if selected upstream.")
cols[2].markdown("**Media rights stay yours**\n\nUse images, footage and scripts you have permission to use. Stock provider terms still apply; outputs are not automatically licensed for every use.")
st.caption("Official project: harry0703/MoneyPrinterTurbo (MIT). Install package `mpt`, not the unrelated third-party PyPI package `MoneyPrinterTurbo`.")
