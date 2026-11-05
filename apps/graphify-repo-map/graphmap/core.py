"""Graphify subprocess adapter and pure graph/token analytics."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Iterable
from urllib.parse import urlparse

import networkx as nx

MAX_SOURCE_BYTES = 2_000_000


class GraphifyError(RuntimeError):
    """An actionable Graphify or source-loading error."""


def github_repo(url: str) -> tuple[str, str, str]:
    """Validate a public GitHub HTTPS URL; return owner, repo, canonical URL."""
    value = url.strip()
    if not value:
        raise ValueError("Paste a GitHub repository URL.")
    parsed = urlparse(value if "://" in value else f"https://{value}")
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise ValueError("Only public https://github.com/owner/repository URLs are supported.")
    if parsed.username or parsed.password or parsed.port:
        raise ValueError("Credentials and custom ports are not accepted.")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in parts):
        raise ValueError("Use exactly https://github.com/owner/repository (no subpaths).")
    owner, repo = parts
    repo = repo.removesuffix(".git")
    if not repo:
        raise ValueError("Repository name is missing.")
    return owner, repo, f"https://github.com/{owner}/{repo}.git"


def clone_public_repo(url: str, destination: Path, timeout: int = 120) -> None:
    _, _, canonical = github_repo(url)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", "--single-branch", canonical, str(destination)],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode:
        raise GraphifyError(f"Could not clone that public repository: {result.stderr.strip()[-800:]}")


def extract_graph(source: Path, output: Path, timeout: int = 300) -> dict:
    """Run the actual graphifyy CLI in local AST-only mode."""
    result = subprocess.run(
        ["graphify", "extract", str(source), "--code-only", "--out", str(output)],
        capture_output=True, text=True, timeout=timeout,
    )
    graph_path = output / "graphify-out" / "graph.json"
    if result.returncode or not graph_path.exists():
        raise GraphifyError(f"Graphify extraction failed: {(result.stderr or result.stdout).strip()[-1200:]}")
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    data["_log"] = result.stdout.strip()
    return data


def to_networkx(data: dict) -> nx.DiGraph:
    """Graphify 0.9 uses JSON-node-link's `links`, not `edges`."""
    graph = nx.DiGraph()
    for node in data.get("nodes", []):
        if isinstance(node, dict) and node.get("id") is not None:
            graph.add_node(str(node["id"]), **{k: v for k, v in node.items() if k != "id"})
    for edge in data.get("links", data.get("edges", [])):
        if isinstance(edge, dict) and edge.get("source") is not None and edge.get("target") is not None:
            graph.add_edge(str(edge["source"]), str(edge["target"]),
                           **{k: v for k, v in edge.items() if k not in {"source", "target"}})
    return graph


def hubs(graph: nx.Graph, limit: int = 30) -> list[dict]:
    rows = []
    for node in graph.nodes:
        attrs = graph.nodes[node]
        if not attrs.get("_callable"):
            continue
        degree = graph.degree(node)
        rows.append({
            "id": node, "symbol": attrs.get("label", node), "connections": degree,
            "kind": "class" if attrs.get("_callable_class") else "function",
            "file": attrs.get("source_file", "external"),
            "location": attrs.get("source_location", ""),
            "community": attrs.get("community"),
        })
    return sorted(rows, key=lambda row: (-row["connections"], row["symbol"]))[:limit]


def communities(graph: nx.Graph) -> list[dict]:
    groups: dict[str, list[str]] = {}
    for node, attrs in graph.nodes(data=True):
        if attrs.get("_callable") and attrs.get("community") is not None:
            groups.setdefault(str(attrs["community"]), []).append(node)
    result = []
    for label, nodes in groups.items():
        ranked = sorted(nodes, key=lambda n: graph.degree(n), reverse=True)
        files = {graph.nodes[n].get("source_file", "external") for n in nodes}
        result.append({"community": label, "symbols": len(nodes), "files": len(files),
                       "top_symbols": ", ".join(graph.nodes[n].get("label", n) for n in ranked[:6]),
                       "node_ids": nodes})
    return sorted(result, key=lambda row: (-row["symbols"], row["community"]))


def symbol_path(graph: nx.Graph, start: str, end: str) -> list[str]:
    if start not in graph or end not in graph:
        raise ValueError("Both symbols must exist in the graph.")
    try:
        return nx.shortest_path(graph.to_undirected(), start, end)
    except nx.NetworkXNoPath:
        return []


def count_tokens(text: str) -> int:
    """cl100k_base estimate; deliberately dependency-light at call time."""
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except (ImportError, ValueError):
        return math.ceil(len(text) / 4)


def source_files(root: Path, graph: nx.Graph) -> dict[str, str]:
    """Read local source files named by the graph, preventing path escapes."""
    result: dict[str, str] = {}
    root = root.resolve()
    for relative in sorted({a.get("source_file") for _, a in graph.nodes(data=True) if a.get("source_file")}):
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
            if path.is_file() and path.stat().st_size <= MAX_SOURCE_BYTES:
                result[relative] = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
    return result


@dataclass(frozen=True)
class TokenReport:
    full_tokens: int
    focused_tokens: int
    full_files: int
    focused_files: int

    @property
    def saved_tokens(self) -> int:
        return max(0, self.full_tokens - self.focused_tokens)

    @property
    def reduction_percent(self) -> float:
        return 100 * self.saved_tokens / self.full_tokens if self.full_tokens else 0.0


def token_report(files: dict[str, str], selected_files: Iterable[str]) -> TokenReport:
    selected = set(selected_files)
    full = sum(count_tokens(text) for text in files.values())
    focused = sum(count_tokens(text) for name, text in files.items() if name in selected)
    return TokenReport(full, focused, len(files), len(selected & set(files)))


def path_report(graph: nx.Graph, path: list[str]) -> str:
    lines = ["# Focused codebase context", "", f"Path length: {max(0, len(path)-1)} hops", ""]
    for index, node in enumerate(path):
        attrs = graph.nodes[node]
        lines.append(f"{index + 1}. **{attrs.get('label', node)}** — `{attrs.get('source_file', 'external')}:{attrs.get('source_location', '')}`")
        if index < len(path) - 1:
            edge = graph.get_edge_data(node, path[index + 1]) or graph.get_edge_data(path[index + 1], node) or {}
            lines.append(f"   ↓ `{edge.get('relation', 'related')}`")
    return "\n".join(lines)
