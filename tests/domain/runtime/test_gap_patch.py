"""Unit tests for GapClass, GapClassification, GraphPatch, MeasurableImprovement (M009 S01)."""

from __future__ import annotations

import pytest

from active_skill_system.domain.runtime import (
    GapClass,
    GapClassification,
    GraphPatch,
    NodeKind,
    PatchOp,
    Severity,
    TaskGraph,
    TaskNode,
    TaskNodeId,
    is_measurable_improvement,
    severity_rank,
)

# ── GapClass ──────────────────────────────────────────────────────────────


def test_all_8_gap_classes_present() -> None:
    expected = {
        "missing_evidence",
        "ambiguity",
        "missing_mechanism",
        "contradiction",
        "constraint_violation",
        "tool_failure",
        "undefined_concept",
        "unsafe_action",
    }
    assert {gc.value for gc in GapClass} == expected


def test_severity_priority_ordering() -> None:
    """critical=0 < high=1 < medium=2 < low=3."""
    assert severity_rank(Severity.CRITICAL) < severity_rank(Severity.HIGH)
    assert severity_rank(Severity.HIGH) < severity_rank(Severity.MEDIUM)
    assert severity_rank(Severity.MEDIUM) < severity_rank(Severity.LOW)


# ── GapClassification ─────────────────────────────────────────────────────


def test_gap_classification_constructs() -> None:
    g = GapClassification(
        node_id=TaskNodeId("g1"),
        gap_class=GapClass.MISSING_EVIDENCE,
        severity=Severity.CRITICAL,
        proposed_action="search",
    )
    assert g.gap_class is GapClass.MISSING_EVIDENCE
    assert g.severity is Severity.CRITICAL


def test_gap_classification_rejects_empty_action() -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        GapClassification(
            node_id=TaskNodeId("g1"),
            gap_class=GapClass.MISSING_EVIDENCE,
            severity=Severity.LOW,
            proposed_action="",
        )


def test_gap_classification_rejects_non_tasknodeid() -> None:
    with pytest.raises(ValueError, match="node_id"):
        GapClassification(
            node_id="plain-string",  # type: ignore[arg-type]
            gap_class=GapClass.MISSING_EVIDENCE,
            severity=Severity.LOW,
            proposed_action="x",
        )


# ── GraphPatch ────────────────────────────────────────────────────────────


def test_graph_patch_add_node() -> None:
    p = GraphPatch(
        operations=(
            PatchOp(op_type="add_node", payload={"node_id": "n1", "kind": "fact", "text": "X"}),
        )
    )
    g = p.apply(TaskGraph())
    assert g.version == 1
    assert len(g.nodes) == 1


def test_graph_patch_add_edge_after_nodes() -> None:
    p = GraphPatch(
        operations=(
            PatchOp(op_type="add_node", payload={"node_id": "a", "kind": "fact", "text": "A"}),
            PatchOp(op_type="add_node", payload={"node_id": "b", "kind": "fact", "text": "B"}),
            PatchOp(op_type="add_edge", payload={"source": "a", "target": "b", "kind": "supports"}),
        )
    )
    g = p.apply(TaskGraph())
    assert g.version == 3
    assert len(g.edges) == 1


def test_graph_patch_rejects_empty_operations() -> None:
    with pytest.raises(ValueError, match="non-empty tuple"):
        GraphPatch(operations=())  # type: ignore[arg-type]


def test_graph_patch_rejects_invalid_op_type() -> None:
    with pytest.raises(ValueError, match="add_node, add_edge"):
        PatchOp(op_type="bogus", payload={"x": "y"})


def test_graph_patch_update_claim_status_is_graph_noop() -> None:
    """update_claim_status is a no-op at graph level (Claim.with_status lives elsewhere)."""
    p = GraphPatch(
        operations=(
            PatchOp(op_type="update_claim_status", payload={"claim_id": "c1", "new_status": "verified"}),
        )
    )
    g0 = TaskGraph().add_node(TaskNode(TaskNodeId("n"), NodeKind.FACT, "X"))
    g1 = p.apply(g0)
    assert g1.version == g0.version  # no-op: graph unchanged
    assert len(g1.nodes) == len(g0.nodes)


# ── MeasurableImprovement gate ───────────────────────────────────────────


def test_gate_accepts_gaps_decrease() -> None:
    assert is_measurable_improvement(
        gaps_before=3, gaps_after=1, constraints_before=0, constraints_after=0,
        verified_before=0, verified_after=0,
    )


def test_gate_accepts_verified_increase() -> None:
    assert is_measurable_improvement(
        gaps_before=2, gaps_after=2, constraints_before=0, constraints_after=0,
        verified_before=0, verified_after=1,
    )


def test_gate_rejects_constraint_regression() -> None:
    assert not is_measurable_improvement(
        gaps_before=3, gaps_after=1, constraints_before=0, constraints_after=2,
        verified_before=0, verified_after=0,
    )


def test_gate_rejects_no_improvement() -> None:
    assert not is_measurable_improvement(
        gaps_before=1, gaps_after=1, constraints_before=0, constraints_after=0,
        verified_before=0, verified_after=0,
    )


def test_gate_rejects_constraint_regression_without_improvement() -> None:
    assert not is_measurable_improvement(
        gaps_before=1, gaps_after=1, constraints_before=0, constraints_after=1,
        verified_before=0, verified_after=0,
    )


# ── R002: domain infra-free ───────────────────────────────────────────────


def test_gap_patch_modules_are_infra_free() -> None:
    import importlib
    from pathlib import Path

    for mod_name in (
        "active_skill_system.domain.runtime.gap",
        "active_skill_system.domain.runtime.patch",
    ):
        mod = importlib.import_module(mod_name)
        src = Path(mod.__file__).read_text()
        for forbidden in (
            "import activegraph",
            "from activegraph",
            "import anthropic",
            "import openai",
        ):
            assert forbidden not in src, f"{mod_name} must not contain '{forbidden}' (R002)"
