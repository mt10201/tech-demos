"""Safe, transparent adapter around the official MoneyPrinterTurbo CLI."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
import uuid

ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
MATERIAL_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm", ".avi", ".mkv"}
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
SECRET_KEY = re.compile(r"(api_?key|token|secret|password)", re.I)


@dataclass(frozen=True)
class VideoRequest:
    topic: str
    script: str = ""
    aspect: str = "9:16"
    source: str = "local"
    materials: tuple[str, ...] = ()
    voice: str = "en-US-AriaNeural"
    clip_duration: int = 5

    def validate(self) -> None:
        if not self.topic.strip():
            raise ValueError("Give your video a topic.")
        if self.aspect not in ASPECTS:
            raise ValueError("Choose a supported aspect ratio.")
        if self.source not in {"local", "pexels", "pixabay"}:
            raise ValueError("Choose local, Pexels or Pixabay materials.")
        if self.source == "local" and not self.materials:
            raise ValueError("Upload at least one local image or video.")
        if not self.voice.startswith(("en-US-", "en-GB-", "zh-CN-")) or self.voice.endswith("-"):
            raise ValueError("Choose an available Edge TTS voice.")
        if not 1 <= self.clip_duration <= 15:
            raise ValueError("Clip duration must be between 1 and 15 seconds.")


@dataclass
class TaskResult:
    task_id: str
    videos: list[str]
    script: str = ""
    log: str = ""


@dataclass
class Readiness:
    mpt_found: bool
    llm_configured: bool
    stock_keys: dict[str, bool]
    mpt_home: Path
    notes: list[str] = field(default_factory=list)


def default_home() -> Path:
    return Path(os.environ.get("MPT_LAB_HOME", Path.home() / ".moneyprinter-short-video-lab")).expanduser()


def mpt_executable() -> str | None:
    # Prefer the mpt next to the Python running Streamlit: activating .venv matters.
    for name in ("mpt.exe", "mpt") if os.name == "nt" else ("mpt",):
        candidate = Path(sys.executable).with_name(name)
        if candidate.is_file():
            return str(candidate)
    return shutil.which("mpt")


def _configured(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def inspect_readiness(home: Path | None = None, executable: str | None = None) -> Readiness:
    """Read only boolean key presence; never return or display secret values."""
    home = home or default_home()
    result = Readiness(bool(executable or mpt_executable()), False, {"pexels": False, "pixabay": False}, home)
    config_path = home / "config.toml"
    if not config_path.is_file():
        result.notes.append("MoneyPrinterTurbo creates config.toml on its first run.")
        return result
    try:
        with config_path.open("rb") as handle:
            config = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        result.notes.append(f"Could not read local configuration: {exc}")
        return result
    app = config.get("app", {})
    provider = app.get("llm_provider", "")
    result.llm_configured = _configured(app.get(f"{provider}_api_key")) if _configured(provider) else False
    def keys_present(name):
        value = app.get(name, [])
        return any(_configured(key) for key in value) if isinstance(value, list) else _configured(value)
    result.stock_keys = {
        "pexels": keys_present("pexels_api_keys"),
        "pixabay": keys_present("pixabay_api_keys"),
    }
    return result


def save_uploads(files, folder: Path) -> tuple[str, ...]:
    """Validate and copy Streamlit UploadedFile-like objects into local storage."""
    if len(files) > 12:
        raise ValueError("Use at most 12 local materials for one demo video.")
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, file in enumerate(files):
        suffix = Path(file.name).suffix.lower()
        if suffix not in MATERIAL_EXTENSIONS:
            raise ValueError(f"Unsupported material type: {file.name}")
        data = file.getvalue()
        if not data or len(data) > MAX_UPLOAD_BYTES:
            raise ValueError(f"{file.name} is empty or exceeds 200 MB.")
        path = folder / f"{index:02d}{suffix}"
        path.write_bytes(data)
        paths.append(str(path.resolve()))
    return tuple(paths)


def build_command(request: VideoRequest, home: Path, task_id: str | None = None) -> tuple[list[str], dict[str, str]]:
    request.validate()
    executable = mpt_executable()
    if not executable:
        raise RuntimeError("Official mpt executable not found. Activate the app's .venv and install requirements.txt.")
    task_id = task_id or str(uuid.uuid4())
    args = [executable, "cli", "--video-subject", request.topic.strip(),
            "--video-source", request.source, "--video-aspect", request.aspect,
            "--video-clip-duration", str(request.clip_duration), "--voice-name", request.voice,
            "--bgm-type", "none", "--subtitle-enabled", "--video-concat-mode", "sequential",
            "--n-threads", "2", "--task-id", task_id]
    if request.script.strip():
        args += ["--video-script", request.script.strip()]
    if request.source == "local":
        args += ["--video-materials", ",".join(request.materials)]
    env = os.environ.copy()
    env["MPT_HOME"] = str(home)
    return args, env


def parse_json_output(text: str) -> dict:
    """The CLI can put log lines beside its JSON result; use the final valid object."""
    candidates = [line.strip() for line in text.splitlines() if line.lstrip().startswith("{")]
    for line in reversed(candidates):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "result" in obj:
            return obj
    raise ValueError("MoneyPrinterTurbo finished without a readable task result.")


def redact(text: str) -> str:
    """Avoid echoing configuration secrets if an upstream exception includes them."""
    return re.sub(r"(?i)((?:api[_ -]?key|token|secret|password)\s*[=:]\s*)([^\s,;]+)", r"\1[redacted]", text)


class MoneyPrinterTurboRunner:
    def __init__(self, home: Path | None = None, timeout: int = 1800):
        self.home = home or default_home()
        self.timeout = timeout

    def run(self, request: VideoRequest, on_log=None) -> TaskResult:
        task_id = str(uuid.uuid4())
        self.home.mkdir(parents=True, exist_ok=True)
        args, env = build_command(request, self.home, task_id)
        try:
            process = subprocess.Popen(args, cwd=self.home, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, errors="replace")
        except OSError as exc:
            raise RuntimeError(f"Could not start MoneyPrinterTurbo: {exc}") from exc
        lines: list[str] = []
        try:
            assert process.stdout is not None
            for line in process.stdout:
                line = line.rstrip()
                lines.append(redact(line))
                if on_log:
                    on_log(redact(line))
            code = process.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait()
            raise RuntimeError(f"Render exceeded {self.timeout // 60} minutes and was stopped.") from exc
        output = "\n".join(lines)
        if code:
            tail = "\n".join(lines[-12:])
            raise RuntimeError(f"MoneyPrinterTurbo exited with code {code}.\n\n{tail}")
        try:
            payload = parse_json_output(output)
        except ValueError as exc:
            raise RuntimeError(f"{exc}\n\n{output[-3000:]}") from exc
        result = payload.get("result") or {}
        videos = [str(Path(p).resolve()) for p in result.get("videos", [])]
        for path in videos:
            task_root = (self.home / "storage" / "tasks" / task_id).resolve()
            candidate = Path(path)
            if not candidate.is_relative_to(task_root) or not candidate.is_file() or candidate.stat().st_size == 0:
                raise RuntimeError("The CLI returned an invalid or missing output video.")
        if not videos:
            raise RuntimeError("The task completed but returned no output videos.")
        return TaskResult(payload.get("task_id", task_id), videos, result.get("script", ""), output[-6000:])


def discover_tasks(home: Path) -> list[dict]:
    tasks = []
    root = home / "storage" / "tasks"
    if not root.is_dir():
        return tasks
    for task in root.iterdir():
        video = task / "final-1.mp4"
        if video.is_file() and video.stat().st_size:
            tasks.append({"id": task.name, "path": str(video), "modified": video.stat().st_mtime})
    return sorted(tasks, key=lambda item: item["modified"], reverse=True)
