"""Tests for M053 S05 — Pattern + PatternMatcher."""

from __future__ import annotations

import pytest

from active_skill_system.domain.pattern import (
    GraphView,
    Pattern,
    PatternClause,
    PatternCondition,
    PatternMatcher,
)


def _graph_with_claim(claim_id: str = "c1", status: str = "open") -> GraphView:
    return GraphView(
        vertices={claim_id: {"type": "claim", "status": status}},
        edges=[],
    )


def _graph_with_claim_and_evidence(claim_id: str = "c1", evidence_id: str = "e1") -> GraphView:
    return GraphView(
        vertices={
            claim_id: {"type": "claim", "status": "open"},
            evidence_id: {"type": "evidence"},
        },
        edges=[{"kind": "supports", "source": evidence_id, "target": claim_id}],
    )


# ── PatternClause ──────────────────────────────────────────────────────────


def test_clause_creation_defaults() -> None:
    c = PatternClause(vertex_type="claim")
    assert c.vertex_type == "claim"
    assert c.condition == PatternCondition.EXISTS
    assert c.filter == {}
    assert c.edge_to == {}


def test_clause_rejects_empty_vertex_type() -> None:
    with pytest.raises(ValueError, match="vertex_type must be non-empty"):
        PatternClause(vertex_type="")


def test_clause_rejects_bad_condition() -> None:
    with pytest.raises(ValueError, match="condition must be"):
        PatternClause(vertex_type="claim", condition="invalid")


# ── Pattern ────────────────────────────────────────────────────────────────


def test_pattern_creation() -> None:
    p = Pattern(
        name="claim_without_evidence",
        clauses=(PatternClause(vertex_type="claim"),),
        description="Fires when a claim exists",
    )
    assert p.name == "claim_without_evidence"
    assert len(p.clauses) == 1


def test_pattern_rejects_empty_clauses() -> None:
    with pytest.raises(ValueError, match="clauses must be non-empty"):
        Pattern(name="p", clauses=())


def test_pattern_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="name must be non-empty"):
        Pattern(name="", clauses=(PatternClause(vertex_type="x"),))


# ── PatternMatcher — EXISTS ────────────────────────────────────────────────


def test_matcher_exists_matches() -> None:
    pattern = Pattern(
        name="has_claim",
        clauses=(PatternClause(vertex_type="claim", condition=PatternCondition.EXISTS),),
    )
    matcher = PatternMatcher()
    assert matcher.matches(pattern, _graph_with_claim()) is True


def test_matcher_exists_no_match() -> None:
    pattern = Pattern(
        name="has_evidence",
        clauses=(PatternClause(vertex_type="evidence", condition=PatternCondition.EXISTS),),
    )
    matcher = PatternMatcher()
    assert matcher.matches(pattern, _graph_with_claim()) is False


# ── PatternMatcher — NOT_EXISTS ────────────────────────────────────────────


def test_matcher_not_exists_matches() -> None:
    """NOT EXISTS evidence on a graph with only a claim → matches."""
    pattern = Pattern(
        name="claim_without_evidence",
        clauses=(PatternClause(vertex_type="evidence", condition=PatternCondition.NOT_EXISTS),),
    )
    matcher = PatternMatcher()
    assert matcher.matches(pattern, _graph_with_claim()) is True


def test_matcher_not_exists_no_match() -> None:
    """NOT EXISTS evidence on a graph WITH evidence → no match."""
    pattern = Pattern(
        name="claim_without_evidence",
        clauses=(PatternClause(vertex_type="evidence", condition=PatternCondition.NOT_EXISTS),),
    )
    matcher = PatternMatcher()
    assert matcher.matches(pattern, _graph_with_claim_and_evidence()) is False


# ── PatternMatcher — filter ────────────────────────────────────────────────


def test_matcher_filter_matches() -> None:
    pattern = Pattern(
        name="open_claim",
        clauses=(PatternClause(
            vertex_type="claim", condition=PatternCondition.EXISTS,
            filter={"status": "open"},
        ),),
    )
    matcher = PatternMatcher()
    assert matcher.matches(pattern, _graph_with_claim(status="open")) is True
    assert matcher.matches(pattern, _graph_with_claim(status="closed")) is False


# ── PatternMatcher — edge conditions ───────────────────────────────────────


def test_matcher_edge_condition_outgoing() -> None:
    """Claim WITH supporting evidence → NOT EXISTS (claim without evidence) no longer matches."""
    pattern = Pattern(
        name="claim_without_evidence",
        clauses=(
            PatternClause(vertex_type="claim", condition=PatternCondition.EXISTS),
            PatternClause(
                vertex_type="evidence", condition=PatternCondition.NOT_EXISTS,
                edge_to={"kind": "supports", "target_type": "claim", "direction": "outgoing"},
            ),
        ),
    )
    matcher = PatternMatcher()
    # Graph with evidence → pattern does NOT match (evidence exists with edge).
    assert matcher.matches(pattern, _graph_with_claim_and_evidence()) is False
    # Graph without evidence → pattern matches (no evidence with edge).
    assert matcher.matches(pattern, _graph_with_claim()) is True


# ── PatternMatcher — conjunction ───────────────────────────────────────────


def test_matcher_all_clauses_must_match() -> None:
    """Pattern with 2 clauses: both must match."""
    pattern = Pattern(
        name="open_claim_no_evidence",
        clauses=(
            PatternClause(
                vertex_type="claim", condition=PatternCondition.EXISTS,
                filter={"status": "open"},
            ),
            PatternClause(vertex_type="evidence", condition=PatternCondition.NOT_EXISTS),
        ),
    )
    matcher = PatternMatcher()
    assert matcher.matches(pattern, _graph_with_claim(status="open")) is True
    assert matcher.matches(pattern, _graph_with_claim(status="closed")) is False


# ── find_matching_vertices ─────────────────────────────────────────────────


def test_find_matching_vertices() -> None:
    graph = GraphView(
        vertices={
            "c1": {"type": "claim", "status": "open"},
            "c2": {"type": "claim", "status": "closed"},
            "e1": {"type": "evidence"},
        },
        edges=[],
    )
    matcher = PatternMatcher()
    clause = PatternClause(vertex_type="claim", filter={"status": "open"})
    result = matcher.find_matching_vertices(clause, graph)
    assert result == ["c1"]


# ── Empty graph ────────────────────────────────────────────────────────────


def test_empty_graph_exists_no_match() -> None:
    pattern = Pattern(
        name="any_claim",
        clauses=(PatternClause(vertex_type="claim", condition=PatternCondition.EXISTS),),
    )
    matcher = PatternMatcher()
    assert matcher.matches(pattern, GraphView()) is False


def test_empty_graph_not_exists_matches() -> None:
    pattern = Pattern(
        name="no_claims",
        clauses=(PatternClause(vertex_type="claim", condition=PatternCondition.NOT_EXISTS),),
    )
    matcher = PatternMatcher()
    assert matcher.matches(pattern, GraphView()) is True
