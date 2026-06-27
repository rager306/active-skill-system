"""Tests for LoopGraph provenance projection (RGLA, D009 §4.2)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from active_skill_system.domain.loop import (
    Budget,
    Loop,
    LoopEvent,
    LoopEventKind,
    LoopState,
)
from active_skill_system.domain.loop_graph import (
    PROVENANCE_EDGE_KINDS,
    RUNTIME_EDGE_KINDS,
    LoopEdge,
    LoopEdgeKind,
    LoopGraph,
    LoopVertex,
    LoopVertexKind,
    project,
)

# ── Vertex / Edge invariants ──────────────────────────────────────────


def test_vertex_rejects_empty_id():
    with pytest.raises(ValueError):
        LoopVertex(id="", kind=LoopVertexKind.LOOP)


def test_vertex_rejects_invalid_kind():
    with pytest.raises(ValueError):
        LoopVertex(id="loop:1", kind="not-a-kind")  # type: ignore[arg-type]


def test_edge_rejects_empty_endpoints():
    with pytest.raises(ValueError):
        LoopEdge(LoopEdgeKind.USES, "", "skill:1")
    with pytest.raises(ValueError):
        LoopEdge(LoopEdgeKind.USES, "loop:1", "  ")


def test_edge_rejects_invalid_kind():
    with pytest.raises(ValueError):
        LoopEdge("uses", "loop:1", "skill:1")  # type: ignore[arg-type]


def test_edge_and_vertex_are_frozen():
    v = LoopVertex(id="loop:1", kind=LoopVertexKind.LOOP)
    with pytest.raises(FrozenInstanceError):
        v.label = "x"  # type: ignore[misc]
    e = LoopEdge(LoopEdgeKind.USES, "loop:1", "skill:1")
    with pytest.raises(FrozenInstanceError):
        e.src = "loop:2"  # type: ignore[misc]


def test_runtime_vs_provenance_edge_partition():
    assert LoopEdgeKind.USES in RUNTIME_EDGE_KINDS
    assert LoopEdgeKind.VERIFIED_BY in PROVENANCE_EDGE_KINDS
    assert RUNTIME_EDGE_KINDS.isdisjoint(PROVENANCE_EDGE_KINDS)


# ── LoopGraph integrity ───────────────────────────────────────────────


def test_graph_rejects_edge_with_unknown_endpoint():
    v = LoopVertex(id="loop:1", kind=LoopVertexKind.LOOP)
    e = LoopEdge(LoopEdgeKind.USES, "loop:1", "skill:missing")  # no such vertex
    with pytest.raises(ValueError, match="dst.*not in vertices"):
        LoopGraph(vertices=(v,), edges=(e,))


def test_graph_query_helpers():
    loop_v = LoopVertex(id="loop:1", kind=LoopVertexKind.LOOP)
    skill_v = LoopVertex(id="skill:s1", kind=LoopVertexKind.SKILL)
    e = LoopEdge(LoopEdgeKind.USES, "loop:1", "skill:s1")
    g = LoopGraph(vertices=(loop_v, skill_v), edges=(e,))
    assert g.vertex("loop:1") is loop_v
    assert g.vertex("nope") is None
    assert g.edges_from("loop:1") == (e,)
    assert g.edges_to("skill:s1") == (e,)
    assert g.has_edge(LoopEdgeKind.USES, "loop:1", "skill:s1")
    assert not g.has_edge(LoopEdgeKind.FIXES, "loop:1", "skill:s1")


# ── project() ─────────────────────────────────────────────────────────


def _loop_with_skills(skills=()) -> Loop:
    return Loop.start("loop-1", "optimize sql", Budget(max_iterations=5), skills=skills)


def test_project_creates_created_and_uses_edges():
    loop = _loop_with_skills(("sql-plan-opt", "iac-plan-opt"))
    g = project(loop)
    assert g.has_edge(LoopEdgeKind.CREATED, "intent:loop-1", "loop:loop-1")
    assert g.has_edge(LoopEdgeKind.USES, "loop:loop-1", "skill:sql-plan-opt")
    assert g.has_edge(LoopEdgeKind.USES, "loop:loop-1", "skill:iac-plan-opt")


def test_project_verified_by_from_verified_event():
    loop = _loop_with_skills(("sql-plan-opt",))
    loop = loop.advance(LoopEvent.now(
        LoopEventKind.VERIFIED, LoopState.VERIFYING,
        {"verifier": "gap-detector", "confidence": 0.9},
    ))
    g = project(loop)
    assert g.has_edge(LoopEdgeKind.VERIFIED_BY, "loop:loop-1", "verifier:gap-detector")
    edge = next(e for e in g.edges if e.kind is LoopEdgeKind.VERIFIED_BY)
    assert edge.payload["confidence"] == 0.9


def test_project_learns_from_unfixed_failure():
    loop = _loop_with_skills(("sql-plan-opt",))
    loop = loop.advance(LoopEvent.now(
        LoopEventKind.FAILED, LoopState.FAILED, {"failure": "timeout"},
    ))
    g = project(loop)
    assert g.has_edge(LoopEdgeKind.LEARNS_FROM, "loop:loop-1", "failure:timeout")


def test_project_fixes_when_fixes_payload_present():
    loop = _loop_with_skills(("sql-plan-opt",))
    loop = loop.advance(LoopEvent.now(
        LoopEventKind.FAILED, LoopState.FAILED,
        {"failure": "timeout", "fixes": True},
    ))
    g = project(loop)
    assert g.has_edge(LoopEdgeKind.FIXES, "loop:loop-1", "failure:timeout")


def test_project_is_idempotent():
    loop = _loop_with_skills(("sql-plan-opt",))
    loop = loop.advance(LoopEvent.now(
        LoopEventKind.VERIFIED, LoopState.VERIFYING, {"verifier": "v1"},
    ))
    assert project(loop) == project(loop)


def test_project_dedupes_duplicate_edges():
    """Re-projecting a loop with one VERIFIED event yields exactly one edge."""
    loop = _loop_with_skills(("sql-plan-opt",))
    ev = LoopEvent.now(LoopEventKind.VERIFIED, LoopState.VERIFYING, {"verifier": "v1"})
    loop = loop.advance(ev)
    g = project(loop)
    verified_edges = [e for e in g.edges if e.kind is LoopEdgeKind.VERIFIED_BY]
    assert len(verified_edges) == 1


def test_project_rejects_non_loop():
    with pytest.raises(TypeError):
        project("not a loop")  # type: ignore[arg-type]


def test_project_empty_skills_still_has_created_edge():
    loop = _loop_with_skills(())
    g = project(loop)
    assert g.has_edge(LoopEdgeKind.CREATED, "intent:loop-1", "loop:loop-1")
    assert not any(e.kind is LoopEdgeKind.USES for e in g.edges)
