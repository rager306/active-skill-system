"""Tests for M054 S05 — GraphViewBuilder use case."""

from __future__ import annotations

from active_skill_system.application.use_cases.graph_view_builder import GraphViewBuilder
from active_skill_system.domain.pattern import GraphView


def _sample_graph() -> dict:
    """Sample graph with claims, evidence, and edges."""
    return {
        "vertices": {
            "c1": {"type": "claim", "text": "sky is blue"},
            "c2": {"type": "claim", "text": "sky is red"},
            "e1": {"type": "evidence", "text": "photo"},
            "m1": {"type": "memo"},
        },
        "edges": [
            {"kind": "supports", "source": "e1", "target": "c1"},
            {"kind": "contradicts", "source": "c2", "target": "c1"},
        ],
    }


def _builder() -> GraphViewBuilder:
    g = _sample_graph()
    return GraphViewBuilder(vertices=g["vertices"], edges=g["edges"])


# ── filter_by_type ────────────────────────────────────────────────────────


def test_filter_by_type_claims() -> None:
    view = _builder().filter_by_type("claim")
    assert isinstance(view, GraphView)
    assert len(view.vertices) == 2  # c1, c2
    assert "c1" in view.vertices
    assert "c2" in view.vertices
    assert "e1" not in view.vertices


def test_filter_by_type_evidence() -> None:
    view = _builder().filter_by_type("evidence")
    assert len(view.vertices) == 1
    assert "e1" in view.vertices


def test_filter_by_type_empty() -> None:
    view = _builder().filter_by_type("nonexistent")
    assert len(view.vertices) == 0


def test_filter_by_type_includes_edges() -> None:
    """filter_by_type includes edges touching the filtered vertices."""
    view = _builder().filter_by_type("claim")
    # contradicts edge between c2 and c1 — both are claims.
    assert any(e["kind"] == "contradicts" for e in view.edges)


# ── filter_by_edge_kind ──────────────────────────────────────────────────


def test_filter_by_edge_kind_supports() -> None:
    view = _builder().filter_by_edge_kind("supports")
    assert len(view.edges) == 1
    assert view.edges[0]["kind"] == "supports"
    # Endpoints included.
    assert "e1" in view.vertices
    assert "c1" in view.vertices


def test_filter_by_edge_kind_contradicts() -> None:
    view = _builder().filter_by_edge_kind("contradicts")
    assert len(view.edges) == 1
    assert "c2" in view.vertices


def test_filter_by_edge_kind_empty() -> None:
    view = _builder().filter_by_edge_kind("nonexistent")
    assert len(view.edges) == 0
    assert len(view.vertices) == 0


# ── subgraph ─────────────────────────────────────────────────────────────


def test_subgraph_includes_specified_vertices() -> None:
    view = _builder().subgraph(["c1", "e1"])
    assert len(view.vertices) == 2
    assert "c1" in view.vertices
    assert "e1" in view.vertices
    assert "c2" not in view.vertices


def test_subgraph_includes_internal_edges_only() -> None:
    """subgraph only includes edges where BOTH endpoints are in the set."""
    view = _builder().subgraph(["c1", "e1"])
    # supports edge: e1 → c1 — both in set.
    assert any(e["kind"] == "supports" for e in view.edges)
    # contradicts edge: c2 → c1 — c2 NOT in set.
    assert not any(e["kind"] == "contradicts" for e in view.edges)


def test_subgraph_empty() -> None:
    view = _builder().subgraph([])
    assert len(view.vertices) == 0
    assert len(view.edges) == 0


# ── full_view ────────────────────────────────────────────────────────────


def test_full_view() -> None:
    view = _builder().full_view()
    assert len(view.vertices) == 4
    assert len(view.edges) == 2


# ── Empty builder ─────────────────────────────────────────────────────────


def test_empty_builder() -> None:
    builder = GraphViewBuilder(vertices={}, edges=[])
    view = builder.full_view()
    assert len(view.vertices) == 0
    assert len(view.edges) == 0
