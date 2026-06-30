"""Tests for M054 S09 — Diligence reactive behavior pack."""

from __future__ import annotations

import pytest

from active_skill_system.adapters.inmemory_patch_applier import InMemoryPatchApplier
from active_skill_system.application.behaviors.diligence_pack import (
    DILIGENCE_PRESETS,
    evidence_linker_handler_factory,
    evidence_linker_relation_behavior,
    get_diligence_preset,
    list_diligence_presets,
    question_generator_behavior,
    question_generator_handler_factory,
    risk_assessor_handler_factory,
    risk_assessor_relation_behavior,
)
from active_skill_system.application.ports.behavior_runtime import BehaviorContext
from active_skill_system.domain.behavior import BehaviorKind
from active_skill_system.domain.graph_primitives import GraphEvent
from active_skill_system.domain.relation import RelationCardinality

# ── Behavior specs ────────────────────────────────────────────────────────


def test_evidence_linker_relation_spec() -> None:
    rb = evidence_linker_relation_behavior()
    assert rb.name == "diligence_evidence_linker"
    assert rb.relation.kind == "supports"
    assert rb.relation.cardinality == RelationCardinality.MANY_TO_ONE


def test_question_generator_behavior_spec() -> None:
    b = question_generator_behavior()
    assert b.name == "diligence_question_generator"
    assert b.kind == BehaviorKind.EVENT
    assert "claim.created" in b.matcher.event_types


def test_risk_assessor_relation_spec() -> None:
    rb = risk_assessor_relation_behavior()
    assert rb.name == "diligence_risk_assessor"
    assert rb.relation.kind == "contradicts"


# ── Handlers ──────────────────────────────────────────────────────────────


def test_evidence_linker_proposes_patch() -> None:
    applier = InMemoryPatchApplier()
    handler = evidence_linker_handler_factory(applier)

    event = GraphEvent(
        id="e1", type="relation.created",
        payload={"target": "claim-1"},
        actor="test", run_id="r1", timestamp_ns=1,
    )
    ctx = BehaviorContext(event=event)
    handler(ctx)

    assert len(applier.list_pending()) == 1
    proposal = applier.list_pending()[0]
    assert proposal.proposed_by == "diligence_evidence_linker"
    assert proposal.patch["payload"]["new_status"] == "supported"


def test_evidence_linker_no_target_skips() -> None:
    applier = InMemoryPatchApplier()
    handler = evidence_linker_handler_factory(applier)

    event = GraphEvent(
        id="e1", type="relation.created", payload={},
        actor="test", run_id="r1", timestamp_ns=1,
    )
    handler(BehaviorContext(event=event))
    assert len(applier.list_pending()) == 0


def test_question_generator_proposes_question_node() -> None:
    applier = InMemoryPatchApplier()
    handler = question_generator_handler_factory(applier)

    event = GraphEvent(
        id="e1", type="claim.created",
        payload={"claim_id": "c1", "text": "sky is blue"},
        actor="test", run_id="r1", timestamp_ns=1,
    )
    handler(BehaviorContext(event=event))

    assert len(applier.list_pending()) == 1
    proposal = applier.list_pending()[0]
    assert "question" in str(proposal.patch["payload"]["node_id"])
    assert "evidence supports" in proposal.patch["payload"]["text"].lower()


def test_question_generator_no_claim_id_skips() -> None:
    applier = InMemoryPatchApplier()
    handler = question_generator_handler_factory(applier)
    event = GraphEvent(id="e1", type="claim.created", payload={}, actor="t", run_id="r", timestamp_ns=1)
    handler(BehaviorContext(event=event))
    assert len(applier.list_pending()) == 0


def test_risk_assessor_proposes_risk_node() -> None:
    applier = InMemoryPatchApplier()
    handler = risk_assessor_handler_factory(applier)

    event = GraphEvent(
        id="e1", type="relation.created",
        payload={"source": "c1", "target": "c2"},
        actor="test", run_id="r1", timestamp_ns=1,
    )
    handler(BehaviorContext(event=event))

    assert len(applier.list_pending()) == 1
    proposal = applier.list_pending()[0]
    assert "risk" in str(proposal.patch["payload"]["node_id"])
    assert "Contradiction" in proposal.patch["payload"]["text"]


def test_risk_assessor_missing_endpoints_skips() -> None:
    applier = InMemoryPatchApplier()
    handler = risk_assessor_handler_factory(applier)
    event = GraphEvent(
        id="e1", type="relation.created", payload={"source": "c1"},
        actor="t", run_id="r", timestamp_ns=1,
    )
    handler(BehaviorContext(event=event))
    assert len(applier.list_pending()) == 0


# ── Registry ──────────────────────────────────────────────────────────────


def test_list_diligence_presets() -> None:
    presets = list_diligence_presets()
    assert "evidence_linker" in presets
    assert "question_generator" in presets
    assert "risk_assessor" in presets


def test_get_diligence_preset_returns_spec_and_handler() -> None:
    applier = InMemoryPatchApplier()
    behavior, handler = get_diligence_preset("question_generator", applier)
    assert behavior.name == "diligence_question_generator"
    assert callable(handler)


def test_get_diligence_preset_unknown_raises() -> None:
    with pytest.raises(KeyError, match="Unknown Diligence preset"):
        get_diligence_preset("nonexistent", InMemoryPatchApplier())


def test_all_presets_in_registry() -> None:
    assert len(DILIGENCE_PRESETS) == 3
