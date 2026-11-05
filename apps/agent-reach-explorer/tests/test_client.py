from __future__ import annotations

import json
import subprocess

import pytest

from reach.client import (AgentReachClient, SOURCES, SearchResponse, SearchResult,
                          extract_json_object, normalize_item, results_csv)


def completed(payload, returncode=0):
    return subprocess.CompletedProcess(["agent-reach"], returncode, json.dumps(payload), "")


def test_only_three_public_sources_are_exposed():
    assert SOURCES == ("github", "youtube", "web")


def test_extract_json_object_ignores_leading_dependency_logs():
    payload = extract_json_object('notice: downloading\n{"ok": true, "items": []}\n')
    assert payload["ok"] is True


def test_extract_json_object_rejects_non_json():
    with pytest.raises(ValueError, match="no JSON"):
        extract_json_object("command failed")


def test_normalize_github_details():
    result = normalize_item("github", {
        "title": "owner/repo", "url": "https://github.com/owner/repo", "author": "owner",
        "text": "A useful repository",
        "raw": {"language": "Python", "stargazers_count": 1234, "license": "MIT"},
    })
    assert result.title == "owner/repo"
    assert result.detail == "Python · 1,234 stars · MIT"


def test_normalize_youtube_duration_views_and_missing_fields():
    result = normalize_item("youtube", {"title": "Video", "url": "https://youtu.be/abc",
                                        "raw": {"duration": 375, "view_count": 22853}})
    assert result.detail == "6:15 · 22,853 views"
    assert result.author == ""


def test_normalize_web_handles_nulls_and_non_dict_raw():
    result = normalize_item("web", {"title": None, "url": None, "author": None, "raw": None})
    assert result.title == "Untitled result"
    assert result.url == ""
    assert result.detail == ""


def test_search_builds_bounded_cli_command_and_normalizes(tmp_path):
    executable = tmp_path / "agent-reach"
    executable.write_text("")
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return completed({"ok": True, "backend": "github-api", "items": [
            {"title": "one", "url": "https://example.com"},
            {"title": "two", "url": "https://example.com/2"},
        ], "meta": {"elapsed_ms": 42}})

    response = AgentReachClient(str(executable), timeout=12, runner=runner).search("github", " agents ", 1)
    assert calls[0][0][1:5] == ["github", "search", "agents", "--limit"]
    assert calls[0][1]["timeout"] == 17
    assert calls[0][1]["check"] is False
    assert response.results[0].title == "one"
    assert len(response.results) == 1
    assert response.elapsed_ms == 42


def test_missing_executable_is_actionable(tmp_path):
    response = AgentReachClient(str(tmp_path / "missing")).search("web", "query")
    assert "CLI not found" in response.error
    assert response.results == []


def test_invalid_source_never_runs_command():
    response = AgentReachClient("missing").search("twitter", "query")
    assert response.error == "Unsupported source"


def test_empty_query_never_runs_command():
    response = AgentReachClient("missing").search("web", "  ")
    assert response.error == "Enter a search query"


def test_cli_error_and_hint_are_preserved(tmp_path):
    executable = tmp_path / "agent-reach"
    executable.write_text("")
    response = AgentReachClient(str(executable), runner=lambda *a, **k: completed({
        "ok": False, "backend": "exa", "error": {"message": "rate limited", "hint": "wait"}
    })).search("web", "query")
    assert response.error == "rate limited — wait"
    assert response.backend == "exa"


def test_timeout_is_isolated_to_source(tmp_path):
    executable = tmp_path / "agent-reach"
    executable.write_text("")

    def runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 10)

    response = AgentReachClient(str(executable), timeout=10, runner=runner).search("youtube", "query")
    assert "timed out after 10 seconds" in response.error


def test_malformed_cli_output_becomes_source_error(tmp_path):
    executable = tmp_path / "agent-reach"
    executable.write_text("")
    process = subprocess.CompletedProcess([], 0, "not json", "")
    response = AgentReachClient(str(executable), runner=lambda *a, **k: process).search("web", "query")
    assert "Could not read Agent Reach output" in response.error


def test_csv_is_combined_and_excel_compatible():
    responses = [SearchResponse("github", [SearchResult("github", "Repo", "https://example.com", text="Description")]),
                 SearchResponse("web", error="blocked")]
    data = results_csv(responses)
    assert data.startswith(b"\xef\xbb\xbf")
    assert b"Repo" in data
    assert b"blocked" not in data


def test_csv_formula_content_is_quoted_not_executed_by_app():
    result = SearchResult("web", "=not-a-formula-to-this-app", "https://example.com")
    decoded = results_csv([SearchResponse("web", [result])]).decode("utf-8-sig")
    assert "'=not-a-formula-to-this-app" in decoded
