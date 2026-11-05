import json
from pathlib import Path
from unittest.mock import Mock

import networkx as nx
import pytest

from graphmap.core import (GraphifyError, communities, extract_graph, github_repo, hubs,
                           source_files, symbol_path, to_networkx, token_report)


def sample_data():
    return {"graph": {"schema_version": 1}, "nodes": [
        {"id": "a", "label": "detect()", "_callable": True, "source_file": "hmm.py", "source_location": "L4", "community": 1},
        {"id": "b", "label": "transform()", "_callable": True, "source_file": "frame.py", "source_location": "L9", "community": 1},
        {"id": "c", "label": "Exporter", "_callable": True, "_callable_class": True, "source_file": "csv.py", "source_location": "L2", "community": 2},
        {"id": "pd", "label": "pandas"},
    ], "links": [
        {"source": "a", "target": "b", "relation": "calls"},
        {"source": "b", "target": "c", "relation": "calls"},
        {"source": "a", "target": "pd", "relation": "calls"},
    ]}


def test_graphify_links_schema_and_external_node():
    graph = to_networkx(sample_data())
    assert graph.number_of_nodes() == 4
    assert graph["a"]["b"]["relation"] == "calls"


def test_edges_fallback_schema():
    data = sample_data(); data["edges"] = data.pop("links")
    assert to_networkx(data).number_of_edges() == 3


def test_hubs_callable_degree_and_kind():
    rows = hubs(to_networkx(sample_data()))
    assert [r["id"] for r in rows] == ["a", "b", "c"]
    assert rows[0]["connections"] == 2
    assert rows[-1]["kind"] == "class"


def test_hubs_limit():
    assert len(hubs(to_networkx(sample_data()), 2)) == 2


def test_communities_group_and_rank():
    rows = communities(to_networkx(sample_data()))
    assert rows[0]["community"] == "1"
    assert rows[0]["symbols"] == 2
    assert "detect()" in rows[0]["top_symbols"]


def test_shortest_path_across_reverse_edge():
    assert symbol_path(to_networkx(sample_data()), "c", "a") == ["c", "b", "a"]


def test_no_path_returns_empty():
    graph = to_networkx(sample_data()); graph.add_node("orphan", _callable=True)
    assert symbol_path(graph, "a", "orphan") == []


def test_missing_symbol_is_actionable():
    with pytest.raises(ValueError, match="Both symbols"):
        symbol_path(nx.Graph(), "x", "y")


@pytest.mark.parametrize("url", ["https://github.com/org/repo", "github.com/org/repo", "https://github.com/org/repo.git"])
def test_github_urls(url):
    assert github_repo(url)[2] == "https://github.com/org/repo.git"


@pytest.mark.parametrize("url", ["https://gitlab.com/org/repo", "https://github.com/org/repo/tree/main", "https://user:pass@github.com/org/repo", "file:///tmp/repo"])
def test_unsafe_or_unsupported_urls(url):
    with pytest.raises(ValueError): github_repo(url)


def test_token_report_and_zero_denominator():
    report = token_report({"a.py": "abcd" * 100, "b.py": "efgh" * 100}, {"a.py"})
    assert report.focused_tokens < report.full_tokens
    assert report.saved_tokens == report.full_tokens - report.focused_tokens
    assert 0 < report.reduction_percent < 100
    assert token_report({}, {}).reduction_percent == 0


def test_source_files_stays_inside_root(tmp_path):
    (tmp_path / "ok.py").write_text("print('ok')")
    graph = nx.DiGraph()
    graph.add_node("a", source_file="ok.py")
    graph.add_node("b", source_file="../secret.py")
    assert source_files(tmp_path, graph) == {"ok.py": "print('ok')"}


def test_extract_runs_code_only_and_reads_graph(tmp_path, monkeypatch):
    output = tmp_path / "out"
    graph_file = output / "graphify-out" / "graph.json"
    graph_file.parent.mkdir(parents=True)
    graph_file.write_text(json.dumps(sample_data()))
    run = Mock(return_value=Mock(returncode=0, stdout="ok", stderr=""))
    monkeypatch.setattr("graphmap.core.subprocess.run", run)
    result = extract_graph(Path("/repo"), output)
    command = run.call_args.args[0]
    assert command[:2] == ["graphify", "extract"]
    assert "--code-only" in command
    assert result["_log"] == "ok"


def test_extract_failure_has_process_output(tmp_path, monkeypatch):
    monkeypatch.setattr("graphmap.core.subprocess.run", Mock(return_value=Mock(returncode=1, stdout="", stderr="bad parser")))
    with pytest.raises(GraphifyError, match="bad parser"):
        extract_graph(Path("/repo"), tmp_path)
