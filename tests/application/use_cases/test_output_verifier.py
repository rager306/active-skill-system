"""Unit tests for OutputVerifierUseCase (M013 S01)."""

from __future__ import annotations

from active_skill_system.application.use_cases.output_verifier import (
    OutputVerifierUseCase,
    VerifierType,
)
from active_skill_system.domain.runtime import (
    EdgeKind,
    NodeKind,
    TaskEdge,
    TaskGraph,
    TaskNode,
    TaskNodeId,
)


def _grounded_graph() -> TaskGraph:
    """Graph with a goal supported by a fact (no ungrounded claims)."""
    return (
        TaskGraph()
        .add_node(TaskNode(TaskNodeId("ev"), NodeKind.EVIDENCE, ""))
        .add_node(TaskNode(TaskNodeId("goal"), NodeKind.GOAL, "G"))
        .add_edge(TaskEdge(TaskNodeId("ev"), TaskNodeId("goal"), EdgeKind.SUPPORTS))
    )


def _empty_graph() -> TaskGraph:
    return TaskGraph()


def _graph_with_ungrounded_claim() -> TaskGraph:
    return (
        TaskGraph()
        .add_node(TaskNode(TaskNodeId("c"), NodeKind.CLAIM, "ungrounded"))
        .add_node(TaskNode(TaskNodeId("goal"), NodeKind.GOAL, "G"))
    )


def test_verify_passes_on_grounded_graph_with_answer() -> None:
    result = OutputVerifierUseCase().verify("Paris is the capital.", _grounded_graph())
    assert result.passed is True
    assert all(c.passed for c in result.checks)


def test_verify_fails_on_empty_answer() -> None:
    result = OutputVerifierUseCase().verify("", _grounded_graph())
    assert result.passed is False
    schema_check = next(c for c in result.checks if c.verifier_type == VerifierType.SCHEMA)
    assert schema_check.passed is False


def test_verify_fails_on_ungrounded_claims() -> None:
    result = OutputVerifierUseCase().verify("answer", _graph_with_ungrounded_claim())
    assert result.passed is False
    cit_check = next(c for c in result.checks if c.verifier_type == VerifierType.CITATION_COVERAGE)
    assert cit_check.passed is False


def test_verify_fails_on_empty_graph() -> None:
    """Empty graph has no goals → type_check fails."""
    result = OutputVerifierUseCase().verify("answer", _empty_graph())
    assert result.passed is False


def test_verify_records_all_four_gates() -> None:
    result = OutputVerifierUseCase().verify("answer", _grounded_graph())
    gate_types = {c.verifier_type for c in result.checks}
    assert gate_types == {
        VerifierType.SCHEMA,
        VerifierType.CITATION_COVERAGE,
        VerifierType.TYPE_CHECK,
        VerifierType.REPLAY_HASH,
    }


def test_verify_summary_describes_failures() -> None:
    result = OutputVerifierUseCase().verify("", _empty_graph())
    assert "gate(s) failed" in result.summary
    assert "2 gate(s) failed" in result.summary or "3" in result.summary or "4" in result.summary


def test_verify_replay_hash_always_checks_version() -> None:
    result = OutputVerifierUseCase().verify("answer", _grounded_graph())
    hash_check = next(c for c in result.checks if c.verifier_type == VerifierType.REPLAY_HASH)
    assert hash_check.passed is True
    assert "graph_version" in hash_check.detail
