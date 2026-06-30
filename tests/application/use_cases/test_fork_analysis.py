"""Tests for M054 S12 — ForkAnalysis use case."""

from __future__ import annotations

import pytest

from active_skill_system.adapters.event_store_impl import EventStoreImpl
from active_skill_system.adapters.inmemory_event_log import InMemoryEventLog
from active_skill_system.application.use_cases.fork_analysis import (
    ForkAnalysisUseCase,
    ReactiveDivergence,
)
from active_skill_system.domain.fork import Diff
from active_skill_system.domain.graph_primitives import GraphEvent


def _store_with_reactive_events() -> EventStoreImpl:
    """Store with parent (behavior A fires 3x) and fork (behavior A fires 1x)."""
    store = EventStoreImpl(InMemoryEventLog())

    # Parent: evidence_check fires 3 times, gap_filler fires 2 times.
    for i in range(3):
        store.append(GraphEvent(
            id=f"p-bt-{i}", type="behavior.triggered",
            payload={"behavior_name": "evidence_check"},
            actor="test", run_id="parent", timestamp_ns=i,
        ))
    for i in range(2):
        store.append(GraphEvent(
            id=f"p-bt2-{i}", type="behavior.triggered",
            payload={"behavior_name": "gap_filler"},
            actor="test", run_id="parent", timestamp_ns=i + 10,
        ))

    # Fork: evidence_check fires 1 time, gap_filler fires 2 times (same).
    store.append(GraphEvent(
        id="f-bt-0", type="behavior.triggered",
        payload={"behavior_name": "evidence_check"},
        actor="test", run_id="fork", timestamp_ns=1,
    ))
    for i in range(2):
        store.append(GraphEvent(
            id=f"f-bt2-{i}", type="behavior.triggered",
            payload={"behavior_name": "gap_filler"},
            actor="test", run_id="fork", timestamp_ns=i + 10,
        ))

    return store


# ── Construction ──────────────────────────────────────────────────────────


def test_fork_analysis_rejects_none_store() -> None:
    with pytest.raises(TypeError, match="event_store must be a non-None"):
        ForkAnalysisUseCase(None)  # type: ignore[arg-type]


# ── ReactiveDivergence ───────────────────────────────────────────────────


def test_reactive_divergence_empty_has_no_divergence() -> None:
    rd = ReactiveDivergence()
    assert rd.has_divergence is False


def test_reactive_divergence_with_diffs_has_divergence() -> None:
    rd = ReactiveDivergence(
        behavior_firings_diff={"evidence_check": (3, 1)},
    )
    assert rd.has_divergence is True


def test_reactive_divergence_summary() -> None:
    rd = ReactiveDivergence(
        behavior_firings_diff={"evidence_check": (3, 1)},
        patch_proposals_diff={"gap_filler": (2, 0)},
    )
    s = rd.summary()
    assert "evidence_check" in s
    assert "parent=3 fork=1" in s
    assert "gap_filler" in s


# ── ForkAnalysisUseCase ──────────────────────────────────────────────────


def test_analyze_detects_behavior_firing_diff() -> None:
    store = _store_with_reactive_events()
    use_case = ForkAnalysisUseCase(store)

    analysis = use_case.analyze("parent", "fork")

    assert analysis.reactive_divergence.has_divergence
    # evidence_check: parent=3, fork=1 → divergent.
    assert "evidence_check" in analysis.reactive_divergence.behavior_firings_diff
    assert analysis.reactive_divergence.behavior_firings_diff["evidence_check"] == (3, 1)
    # gap_filler: parent=2, fork=2 → NOT divergent (same count).
    assert "gap_filler" not in analysis.reactive_divergence.behavior_firings_diff


def test_analyze_no_divergence_when_identical() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    # Both runs have identical events.
    for run_id in ("run-a", "run-b"):
        store.append(GraphEvent(
            id=f"{run_id}-bt", type="behavior.triggered",
            payload={"behavior_name": "test_behavior"},
            actor="test", run_id=run_id, timestamp_ns=1,
        ))

    use_case = ForkAnalysisUseCase(store)
    analysis = use_case.analyze("run-a", "run-b")

    assert analysis.reactive_divergence.has_divergence is False


def test_analyze_with_structural_diff() -> None:
    store = _store_with_reactive_events()
    use_case = ForkAnalysisUseCase(store)

    structural = Diff(
        parent_run_id="parent",
        fork_run_id="fork",
        split_event_id="evt-split-001",
    )

    analysis = use_case.analyze("parent", "fork", structural_diff=structural)

    assert analysis.structural_diff is structural
    assert analysis.split_event_id == "evt-split-001"


def test_analyze_summary() -> None:
    store = _store_with_reactive_events()
    use_case = ForkAnalysisUseCase(store)

    analysis = use_case.analyze("parent", "fork")
    s = analysis.summary()

    assert "parent vs fork" in s
    assert "evidence_check" in s


def test_analyze_detects_patch_proposal_diff() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    # Parent proposes 2 patches, fork proposes 0.
    for i in range(2):
        store.append(GraphEvent(
            id=f"p-pp-{i}", type="patch.proposed",
            payload={"proposed_by": "evidence_check"},
            actor="test", run_id="parent", timestamp_ns=i,
        ))
    # Fork has no patch proposals.

    use_case = ForkAnalysisUseCase(store)
    analysis = use_case.analyze("parent", "fork")

    assert "evidence_check" in analysis.reactive_divergence.patch_proposals_diff
    assert analysis.reactive_divergence.patch_proposals_diff["evidence_check"] == (2, 0)


def test_analyze_detects_policy_decision_diff() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    # Parent approves patch-1, fork rejects patch-1.
    store.append(GraphEvent(
        id="p-pa", type="policy.approved",
        payload={"proposal_id": "patch-1"},
        actor="test", run_id="parent", timestamp_ns=1,
    ))
    store.append(GraphEvent(
        id="f-pr", type="policy.rejected",
        payload={"proposal_id": "patch-1"},
        actor="test", run_id="fork", timestamp_ns=1,
    ))

    use_case = ForkAnalysisUseCase(store)
    analysis = use_case.analyze("parent", "fork")

    assert "patch-1" in analysis.reactive_divergence.policy_decisions_diff
    parent_dec, fork_dec = analysis.reactive_divergence.policy_decisions_diff["patch-1"]
    assert parent_dec == "policy.approved"
    assert fork_dec == "policy.rejected"


def test_analyze_empty_runs() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    use_case = ForkAnalysisUseCase(store)

    analysis = use_case.analyze("nonexistent-a", "nonexistent-b")

    assert analysis.reactive_divergence.has_divergence is False
