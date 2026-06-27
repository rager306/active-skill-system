"""Coverage tests for loop_graph.py uncovered branches (M045 S01 T02)."""

from __future__ import annotations

from active_skill_system.domain.loop import (
    Budget,
    Loop,
    LoopEvent,
    LoopEventKind,
    LoopState,
)
from active_skill_system.domain.loop_graph import (
    LoopEdge,
    LoopEdgeKind,
    LoopGraph,
    LoopVertex,
    LoopVertexKind,
    project,
)


def _loop_with_skills(skills=()) -> Loop:
    return Loop.start("lg-1", "x", Budget(max_iterations=5), skills=skills)


# ── project() FIXES edge ──────────────────────────────────────────────


def test_project_fixes_edge_from_failed_with_fixes():
    loop = _loop_with_skills(("skill-a",))
    loop = loop.advance(LoopEvent.now(
        LoopEventKind.FAILED, LoopState.FAILED,
        {"failure": "timeout", "fixes": True},
    ))
    g = project(loop)
    assert g.has_edge(LoopEdgeKind.FIXES, "loop:lg-1", "failure:timeout")


def test_project_learns_from_without_fixes():
    loop = _loop_with_skills(("skill-a",))
    loop = loop.advance(LoopEvent.now(
        LoopEventKind.FAILED, LoopState.FAILED,
        {"failure": "oom"},
    ))
    g = project(loop)
    assert g.has_edge(LoopEdgeKind.LEARNS_FROM, "loop:lg-1", "failure:oom")
    assert not g.has_edge(LoopEdgeKind.FIXES, "loop:lg-1", "failure:oom")


# ── LoopGraph query helpers ───────────────────────────────────────────


def test_edges_from_and_to_both_directions():
    a = LoopVertex(id="a", kind=LoopVertexKind.LOOP)
    b = LoopVertex(id="b", kind=LoopVertexKind.SKILL)
    e = LoopEdge(LoopEdgeKind.USES, "a", "b")
    g = LoopGraph(vertices=(a, b), edges=(e,))
    # edges_from a → finds edge to b
    from_a = g.edges_from("a")
    assert any(ee.dst == "b" for ee in from_a)
    # edges_to b → finds edge from a
    to_b = g.edges_to("b")
    assert any(ee.src == "a" for ee in to_b)


def test_edges_from_on_empty_graph():
    g = LoopGraph()
    assert g.edges_from("any") == ()


def test_edges_to_on_empty_graph():
    g = LoopGraph()
    assert g.edges_to("any") == ()


def test_vertex_not_found_returns_none():
    g = LoopGraph()
    assert g.vertex("missing") is None


def test_has_edge_false_on_empty_graph():
    g = LoopGraph()
    assert g.has_edge(LoopEdgeKind.USES, "a", "b") is False


# ── LoopVertex/LoopEdge edge cases ────────────────────────────────────


def test_loop_vertex_with_empty_label():
    v = LoopVertex(id="x", kind=LoopVertexKind.LOOP, label="")
    assert v.label == ""


def test_loop_edge_with_empty_payload():
    e = LoopEdge(LoopEdgeKind.USES, "a", "b", payload={})
    assert e.payload == {}


# ── project() idempotency with multiple skills ───────────────────────


def test_project_multiple_skills_all_uses_edges():
    loop = _loop_with_skills(("s1", "s2", "s3"))
    g = project(loop)
    for s in ("s1", "s2", "s3"):
        assert g.has_edge(LoopEdgeKind.USES, "loop:lg-1", f"skill:{s}")


# ── project with verified event carrying confidence ──────────────────


def test_project_verified_with_confidence_payload():
    loop = _loop_with_skills(("s1",))
    loop = loop.advance(LoopEvent.now(
        LoopEventKind.VERIFIED, LoopState.VERIFYING,
        {"verifier": "unit-tests", "confidence": 0.95},
    ))
    g = project(loop)
    assert g.has_edge(LoopEdgeKind.VERIFIED_BY, "loop:lg-1", "verifier:unit-tests")
    edge = next(e for e in g.edges if e.kind is LoopEdgeKind.VERIFIED_BY)
    assert edge.payload["confidence"] == 0.95


# ── project rejects non-Loop ──────────────────────────────────────────


def test_project_rejects_non_loop():
    import pytest
    with pytest.raises(TypeError):
        project("not a loop")  # type: ignore[arg-type]


# ── project with FAILED but no failure key ────────────────────────────


def test_project_failed_event_without_failure_key():
    """A FAILED event without a 'failure' payload produces no FIXES/LEARNS_FROM edge."""
    loop = _loop_with_skills(("s1",))
    loop = loop.advance(LoopEvent.now(
        LoopEventKind.FAILED, LoopState.FAILED, {"reason": "budget"},
    ))
    g = project(loop)
    assert not any(e.kind is LoopEdgeKind.FIXES for e in g.edges)
    assert not any(e.kind is LoopEdgeKind.LEARNS_FROM for e in g.edges)
