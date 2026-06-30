"""L2 Application — Diligence behavior pack (M054 S09).

Full Diligence behavior pack adapted from activegraph's diligence pack.
Three behaviors using RelationBehavior (S00) + GraphView (S05) + PatchApplier:

  - evidence_linker: fires when evidence is created, links it to claims.
  - question_generator: fires on claim.created, generates research questions.
  - risk_assessor: fires when a claim is created, assesses its risk level.

Each is a preset behavior that proposes patches through PatchApplier.
This is the activegraph Diligence pack in our hexagonal architecture.
"""

from __future__ import annotations

from typing import Any

from active_skill_system.application.ports.behavior_runtime import (
    BehaviorContext,
    BehaviorHandler,
)
from active_skill_system.domain.behavior import Behavior, BehaviorKind, EventMatcher
from active_skill_system.domain.relation import Relation, RelationBehavior, RelationCardinality

# ── Evidence Linker ───────────────────────────────────────────────────────


def evidence_linker_relation_behavior() -> RelationBehavior:
    """RelationBehavior: fires when evidence→claim 'supports' edge is created."""
    return RelationBehavior(
        name="diligence_evidence_linker",
        relation=Relation(
            kind="supports",
            source_type="evidence",
            target_type="claim",
            cardinality=RelationCardinality.MANY_TO_ONE,
        ),
        description="Links evidence to claims and marks claims as supported",
    )


def evidence_linker_handler_factory(patch_applier: Any) -> BehaviorHandler:
    """Create evidence_linker handler: marks the claim as having evidence."""
    def handler(ctx: BehaviorContext) -> None:
        target_claim = ctx.event.payload.get("target", "")
        if not target_claim:
            return
        patch_applier.propose(
            proposed_by="diligence_evidence_linker",
            patch={"op_type": "update_claim_status",
                   "payload": {"claim_id": target_claim, "new_status": "supported"}},
            reason="Evidence linked to claim — measurable improvement in grounding",
        )

    return handler


# ── Question Generator ────────────────────────────────────────────────────


def question_generator_behavior() -> Behavior:
    """Behavior: fires on claim.created, generates research questions."""
    return Behavior(
        name="diligence_question_generator",
        matcher=EventMatcher(event_types=("claim.created",)),
        kind=BehaviorKind.EVENT,
        description="Generates research questions for new claims",
    )


def question_generator_handler_factory(patch_applier: Any) -> BehaviorHandler:
    """Create question_generator handler: proposes questions as new nodes."""
    def handler(ctx: BehaviorContext) -> None:
        claim_id = ctx.event.payload.get("claim_id", "")
        claim_text = ctx.event.payload.get("text", "")
        if not claim_id:
            return

        # Simple heuristic: generate a question based on claim text.
        question = f"What evidence supports: {claim_text[:80]}?"
        patch_applier.propose(
            proposed_by="diligence_question_generator",
            patch={"op_type": "add_node",
                   "payload": {"node_id": f"question-{claim_id}",
                               "kind": "question", "text": question}},
            reason="Research question generated for claim — measurable improvement",
        )

    return handler


# ── Risk Assessor ─────────────────────────────────────────────────────────


def risk_assessor_relation_behavior() -> RelationBehavior:
    """RelationBehavior: fires when claim→claim 'contradicts' edge is created."""
    return RelationBehavior(
        name="diligence_risk_assessor",
        relation=Relation(
            kind="contradicts",
            source_type="claim",
            target_type="claim",
            cardinality=RelationCardinality.MANY_TO_MANY,
        ),
        description="Assesses risk when claims contradict each other",
    )


def risk_assessor_handler_factory(patch_applier: Any) -> BehaviorHandler:
    """Create risk_assessor handler: flags contradicted claims as risky."""
    def handler(ctx: BehaviorContext) -> None:
        source_claim = ctx.event.payload.get("source", "")
        target_claim = ctx.event.payload.get("target", "")
        if not source_claim or not target_claim:
            return

        patch_applier.propose(
            proposed_by="diligence_risk_assessor",
            patch={"op_type": "add_node",
                   "payload": {"node_id": f"risk-{source_claim}-{target_claim}",
                               "kind": "risk", "text": "Contradiction detected between claims"}},
            reason="Contradiction creates risk — measurable improvement in hazard detection",
        )

    return handler


# ── Preset registry ────────────────────────────────────────────────────────


DILIGENCE_PRESETS = {
    "evidence_linker": (evidence_linker_relation_behavior, evidence_linker_handler_factory),
    "question_generator": (question_generator_behavior, question_generator_handler_factory),
    "risk_assessor": (risk_assessor_relation_behavior, risk_assessor_handler_factory),
}


def get_diligence_preset(name: str, patch_applier: Any) -> tuple[Any, BehaviorHandler]:
    """Get a Diligence preset behavior + handler by name.

    Returns:
        Tuple of (Behavior or RelationBehavior spec, handler function).
    """
    if name not in DILIGENCE_PRESETS:
        raise KeyError(f"Unknown Diligence preset: {name}. Available: {list(DILIGENCE_PRESETS.keys())}")
    behavior_fn, handler_fn = DILIGENCE_PRESETS[name]
    return behavior_fn(), handler_fn(patch_applier)


def list_diligence_presets() -> list[str]:
    """List available Diligence preset names."""
    return list(DILIGENCE_PRESETS.keys())
