from pathlib import Path
import json
import subprocess

import pytest

from video_lab.runner import (MoneyPrinterTurboRunner, TaskResult, VideoRequest, build_command,
    discover_tasks, inspect_readiness, parse_json_output, redact, save_uploads)


@pytest.fixture
def executable(monkeypatch):
    monkeypatch.setattr("video_lab.runner.mpt_executable", lambda: "/venv/bin/mpt")


def request(**overrides):
    values = dict(topic="Mountain air", script="Take a breath.", materials=("/tmp/one.jpg",))
    values.update(overrides)
    return VideoRequest(**values)


def test_no_key_custom_script_command(executable, tmp_path):
    args, env = build_command(request(), tmp_path, "task-123")
    assert args[:2] == ["/venv/bin/mpt", "cli"]
    assert args[args.index("--video-script") + 1] == "Take a breath."
    assert args[args.index("--video-materials") + 1] == "/tmp/one.jpg"
    assert args[args.index("--video-aspect") + 1] == "9:16"
    assert args[args.index("--voice-name") + 1] == "en-US-AriaNeural"
    assert args[args.index("--bgm-type") + 1] == "none"
    assert "--subtitle-enabled" in args
    assert env["MPT_HOME"] == str(tmp_path)
    assert all(token in args for token in ["tiktok", "youtube", "instagram"]) is False


def test_topic_only_command_leaves_llm_to_upstream(executable, tmp_path):
    args, _ = build_command(request(script=""), tmp_path)
    assert "--video-script" not in args


def test_all_aspect_ratios(executable, tmp_path):
    for aspect in ("9:16", "16:9", "1:1"):
        args, _ = build_command(request(aspect=aspect), tmp_path)
        assert args[args.index("--video-aspect") + 1] == aspect


def test_stock_does_not_pass_local_materials(executable, tmp_path):
    args, _ = build_command(request(source="pexels", materials=()), tmp_path)
    assert "--video-materials" not in args


@pytest.mark.parametrize("changes,message", [
    ({"topic": " "}, "topic"),
    ({"aspect": "4:3"}, "aspect"),
    ({"source": "local", "materials": ()}, "Upload"),
    ({"source": "coverr"}, "local, Pexels"),
    ({"voice": "not-a-voice"}, "voice"),
    ({"clip_duration": 0}, "between"),
])
def test_request_validation(changes, message, executable, tmp_path):
    with pytest.raises(ValueError, match=message):
        build_command(request(**changes), tmp_path)


class Upload:
    def __init__(self, name, data=b"media"):
        self.name, self.data = name, data
    def getvalue(self):
        return self.data


def test_save_uploads_sanitizes_names(tmp_path):
    paths = save_uploads([Upload("../../custom.jpg"), Upload("clip.mp4")], tmp_path)
    assert [Path(p).name for p in paths] == ["00.jpg", "01.mp4"]
    assert all(Path(p).parent == tmp_path for p in paths)


def test_save_uploads_rejects_type_and_size(tmp_path):
    with pytest.raises(ValueError, match="Unsupported"):
        save_uploads([Upload("script.exe")], tmp_path)
    with pytest.raises(ValueError, match="empty"):
        save_uploads([Upload("image.jpg", b"")], tmp_path)


def test_parse_json_output_ignores_logs():
    data = parse_json_output('starting\n{"unrelated": 1}\n{"task_id":"abc","result":{"videos":[]}}\n')
    assert data["task_id"] == "abc"


def test_parse_json_output_rejects_missing_result():
    with pytest.raises(ValueError, match="readable"):
        parse_json_output("no json here")


def test_redact_secret():
    assert "supersecret" not in redact("failed api_key=supersecret")
    assert "[redacted]" in redact("failed api_key=supersecret")


def test_readiness_without_config(tmp_path):
    ready = inspect_readiness(tmp_path, executable="mpt")
    assert ready.mpt_found and not ready.llm_configured
    assert ready.stock_keys == {"pexels": False, "pixabay": False}


def test_readiness_config_never_exposes_secrets(tmp_path):
    (tmp_path / "config.toml").write_text('[app]\nllm_provider="openai"\nopenai_api_key="private"\npexels_api_keys=["stock-private"]\npixabay_api_keys=[]\n')
    ready = inspect_readiness(tmp_path, executable="mpt")
    assert ready.llm_configured and ready.stock_keys["pexels"] and not ready.stock_keys["pixabay"]
    assert "private" not in repr(ready)


def test_discover_tasks_only_nonempty_videos(tmp_path):
    good = tmp_path / "storage/tasks/one"
    good.mkdir(parents=True)
    (good / "final-1.mp4").write_bytes(b"video")
    empty = tmp_path / "storage/tasks/two"
    empty.mkdir()
    (empty / "final-1.mp4").touch()
    tasks = discover_tasks(tmp_path)
    assert len(tasks) == 1 and tasks[0]["id"] == "one"


def test_runner_returns_video_and_log(monkeypatch, tmp_path):
    task = tmp_path / "storage/tasks/known"
    task.mkdir(parents=True)
    video = task / "final-1.mp4"
    video.write_bytes(b"mp4")
    class Stdout:
        def __iter__(self):
            return iter(['log\n', json.dumps({"task_id":"known", "result":{"videos":[str(video)],"script":"Hi"}}) + '\n'])
    class Process:
        stdout = Stdout()
        def wait(self, timeout=None): return 0
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: Process())
    monkeypatch.setattr("video_lab.runner.uuid.uuid4", lambda: "known")
    result = MoneyPrinterTurboRunner(tmp_path).run(request())
    assert isinstance(result, TaskResult) and result.videos == [str(video)] and result.script == "Hi"


def test_runner_raises_bounded_error(monkeypatch, tmp_path):
    class Process:
        stdout = iter(["failure api_key=hidden\n"])
        def wait(self, timeout=None): return 1
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: Process())
    with pytest.raises(RuntimeError) as error:
        MoneyPrinterTurboRunner(tmp_path).run(request())
    assert "code 1" in str(error.value) and "hidden" not in str(error.value)
