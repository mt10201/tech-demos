"""Small, read-only adapter around Agent Reach's JSON CLI.

Only the public github/youtube/web search commands are exposed here. No browser
session, cookie, login or API-key configuration is read or changed by this app.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
import io
import json
import os
import shutil
import subprocess
from typing import Any, Callable, Iterable

SOURCES = ("github", "youtube", "web")


@dataclass
class SearchResult:
    source: str
    title: str
    url: str
    author: str = ""
    published_at: str = ""
    text: str = ""
    detail: str = ""


@dataclass
class SearchResponse:
    source: str
    results: list[SearchResult] = field(default_factory=list)
    error: str = ""
    backend: str = ""
    elapsed_ms: int = 0


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def normalize_item(source: str, item: dict[str, Any]) -> SearchResult:
    """Normalize common v1.6 fields and retain useful source-specific details."""
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
    detail_parts: list[str] = []
    if source == "github":
        language = _text(raw.get("language"))
        if language:
            detail_parts.append(language)
        stars = _integer(raw.get("stargazers_count"))
        if stars:
            detail_parts.append(f"{stars:,} stars")
        license_name = _text(raw.get("license"))
        if license_name:
            detail_parts.append(license_name)
    elif source == "youtube":
        seconds = _integer(raw.get("duration"))
        if seconds:
            detail_parts.append(f"{seconds // 60}:{seconds % 60:02d}")
        views = _integer(raw.get("view_count"))
        if views:
            detail_parts.append(f"{views:,} views")
    return SearchResult(
        source=source,
        title=_text(item.get("title")) or "Untitled result",
        url=_text(item.get("url")),
        author=_text(item.get("author")),
        published_at=_text(item.get("published_at")),
        text=_text(item.get("text")),
        detail=" · ".join(detail_parts),
    )


def extract_json_object(stdout: str) -> dict[str, Any]:
    """Read the CLI's JSON object, tolerating a dependency's leading log lines."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(stdout):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and ("ok" in value or "items" in value):
            return value
    raise ValueError("Agent Reach returned no JSON response")


class AgentReachClient:
    def __init__(
        self,
        executable: str | None = None,
        timeout: int = 90,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.executable = executable or os.environ.get("AGENT_REACH_BIN", "agent-reach")
        self.timeout = timeout
        self.runner = runner

    def search(self, source: str, query: str, limit: int = 5) -> SearchResponse:
        if source not in SOURCES:
            return SearchResponse(source, error="Unsupported source")
        if not query.strip():
            return SearchResponse(source, error="Enter a search query")
        executable = shutil.which(self.executable) if os.path.sep not in self.executable else self.executable
        if not executable or not os.path.exists(executable):
            return SearchResponse(
                source,
                error="Agent Reach CLI not found. Run `pip install -r requirements.txt` in this app's virtual environment.",
            )
        command = [executable, source, "search", query.strip(), "--limit", str(limit), "--timeout", str(self.timeout)]
        try:
            completed = self.runner(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout + 5,
                check=False,
            )
            payload = extract_json_object(completed.stdout)
        except subprocess.TimeoutExpired:
            return SearchResponse(source, error=f"Search timed out after {self.timeout} seconds")
        except (OSError, ValueError) as exc:
            return SearchResponse(source, error=f"Could not read Agent Reach output: {exc}")

        backend = _text(payload.get("backend"))
        elapsed_ms = _integer((payload.get("meta") or {}).get("elapsed_ms")) if isinstance(payload.get("meta"), dict) else 0
        if not payload.get("ok"):
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            message = _text(error.get("message")) or "Search failed"
            hint = _text(error.get("hint"))
            return SearchResponse(source, error=message + (f" — {hint}" if hint else ""), backend=backend, elapsed_ms=elapsed_ms)
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        results = [normalize_item(source, item) for item in items[:limit] if isinstance(item, dict)]
        return SearchResponse(source, results=results, backend=backend, elapsed_ms=elapsed_ms)


def results_csv(responses: Iterable[SearchResponse]) -> bytes:
    """Export normalized results only; failed/empty sources contribute no rows."""
    output = io.StringIO()
    fields = ["source", "title", "url", "author", "published_at", "detail", "text"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for response in responses:
        for result in response.results:
            row = asdict(result)
            for key, value in row.items():
                if value.startswith(("=", "+", "-", "@")):
                    row[key] = "'" + value
            writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")
