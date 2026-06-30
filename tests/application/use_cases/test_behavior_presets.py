"""Tests for M053 S08 — Behavior presets library."""

from __future__ import annotations

import pytest

from active_skill_system.adapters.inmemory_patch_applier import InMemoryPatchApplier
from active_skill_system.application.behaviors.presets import (
    PRESET_BEHAVIORS,
    contradiction_detector_behavior,
    contradiction_detector_handler_factory,
    evidence_check_behavior,
    evidence_check_handler_factory,
    gap_filler_behavior,
    gap_filler_handler_factory,
    get_preset,
    list_presets,
)
from active_skill_system.domain.behavior import BehaviorKind
from active_skill_system.domain.graph_primitives import GraphEvent

# ── Behavior specs ─────────────────────────────────────────────────────────


def test_evidence_check_behavior_spec() -> None:
    b = evidence_check_behavior()
    assert b.name == "evidence_check"
    assert "claim.created" in b.matcher.event_types
    assert b.kind == BehaviorKind.EVENT


def test_contradiction_detector_behavior_spec() -> None:
    b = contradiction_detector_behavior()
    assert b.name == "contradiction_detector"
    assert b.activate_after == 1  # needs existing claims


def test_gap_filler_behavior_spec() -> None:
    b = gap_filler_behavior()
    assert b.name == "gap_filler"
    assert "gap.detected" in b.matcher.event_types


# ── Evidence check handler ─────────────────────────────────────────────────


def test_evidence_check_proposes_patch_when_no_evidence() -> None:
    applier = InMemoryPatchApplier()
    handler = evidence_check_handler_factory(applier)

    # Simulate a claim.created event with no evidence in graph.
    ctx_event = GraphEvent(
        id="e1", type="claim.created", payload={"claim_id": "c1"},
        actor="test", run_id="r1", timestamp_ns=1,
    )
    from active_skill_system.application.ports.behavior_runtime import BehaviorContext
    ctx = BehaviorContext(event=ctx_event, graph_snapshot={})
    handler(ctx)

    assert len(applier.list_pending()) == 1
    proposal = applier.list_pending()[0]
    assert proposal.proposed_by == "evidence_check"


def test_evidence_check_no_patch_when_evidence_exists() -> None:
    applier = InMemoryPatchApplier()
    handler = evidence_check_handler_factory(applier)

    ctx_event = GraphEvent(
        id="e1", type="claim.created", payload={"claim_id": "c1"},
        actor="test", run_id="r1", timestamp_ns=1,
    )
    from active_skill_system.application.ports.behavior_runtime import BehaviorContext
    # Graph has evidence for c1.
    ctx = BehaviorContext(
        event=ctx_event,
        graph_snapshot={"e1": {"type": "evidence", "claim_id": "c1"}},
    )
    handler(ctx)

    assert len(applier.list_pending()) == 0


def test_evidence_check_no_claim_id_skips() -> None:
    applier = InMemoryPatchApplier()
    handler = evidence_check_handler_factory(applier)

    ctx_event = GraphEvent(
        id="e1", type="claim.created", payload={},  # no claim_id
        actor="test", run_id="r1", timestamp_ns=1,
    )
    from active_skill_system.application.ports.behavior_runtime import BehaviorContext
    ctx = BehaviorContext(event=ctx_event, graph_snapshot={})
    handler(ctx)

    assert len(applier.list_pending()) == 0


# ── Gap filler handler ────────────────────────────────────────────────────


def test_gap_filler_proposes_patch() -> None:
    applier = InMemoryPatchApplier()
    handler = gap_filler_handler_factory(applier)

    ctx_event = GraphEvent(
        id="e1", type="gap.detected",
        payload={"gap_type": "missing_evidence", "location": "node-5"},
        actor="test", run_id="r1", timestamp_ns=1,
    )
    from active_skill_system.application.ports.behavior_runtime import BehaviorContext
    ctx = BehaviorContext(event=ctx_event)
    handler(ctx)

    assert len(applier.list_pending()) == 1
    proposal = applier.list_pending()[0]
    assert "fill" in str(proposal.patch)


def test_gap_filler_no_gap_type_skips() -> None:
    applier = InMemoryPatchApplier()
    handler = gap_filler_handler_factory(applier)

    ctx_event = GraphEvent(
        id="e1", type="gap.detected", payload={},
        actor="test", run_id="r1", timestamp_ns=1,
    )
    from active_skill_system.application.ports.behavior_runtime import BehaviorContext
    ctx = BehaviorContext(event=ctx_event)
    handler(ctx)

    assert len(applier.list_pending()) == 0


# ── Contradiction detector handler ─────────────────────────────────────────


def test_contradiction_detector_no_contradiction() -> None:
    applier = InMemoryPatchApplier()
    handler = contradiction_detector_handler_factory(applier)

    ctx_event = GraphEvent(
        id="e1", type="claim.created", payload={"claim_id": "c2", "text": "sky is blue"},
        actor="test", run_id="r1", timestamp_ns=1,
    )
    from active_skill_system.application.ports.behavior_runtime import BehaviorContext
    ctx = BehaviorContext(event=ctx_event, graph_snapshot={
        "c1": {"type": "claim", "text": "grass is green"},
    })
    handler(ctx)

    assert len(applier.list_pending()) == 0


# ── Preset registry ────────────────────────────────────────────────────────


def test_list_presets() -> None:
    presets = list_presets()
    assert "evidence_check" in presets
    assert "contradiction_detector" in presets
    assert "gap_filler" in presets


def test_get_preset_returns_behavior_and_handler() -> None:
    applier = InMemoryPatchApplier()
    behavior, handler = get_preset("evidence_check", applier)
    assert behavior.name == "evidence_check"
    assert callable(handler)


def test_get_preset_unknown_raises() -> None:
    with pytest.raises(KeyError, match="Unknown preset"):
        get_preset("nonexistent", InMemoryPatchApplier())


def test_all_presets_in_registry() -> None:
    assert len(PRESET_BEHAVIORS) == 3
