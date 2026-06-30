"""L2 Application — Behavior presets library (M053 S08).

Pre-built behaviors for common reactive patterns in our domain. These are
the Diligence-pack equivalents adapted to our hexagonal architecture.

Each preset is a Behavior spec + a handler function. Handlers are pure:
they receive a BehaviorContext and return proposed patches (or None).
They don't mutate the graph directly — they propose patches via the
PatchApplier wired in the context.

Presets:
  - EvidenceCheckBehavior: fires on claim.created, detects missing evidence,
    proposes a patch to flag the claim.
  - ContradictionDetectorBehavior: fires on claim.created, detects
    contradictions with existing claims.
  - GapFillerBehavior: fires on gap.detected, proposes a patch to fill the gap.
"""

from __future__ import annotations

from typing import Any

from active_skill_system.application.ports.behavior_runtime import (
    BehaviorContext,
    BehaviorHandler,
)
from active_skill_system.domain.behavior import Behavior, BehaviorKind, EventMatcher

# ── Evidence Check ─────────────────────────────────────────────────────────


def evidence_check_behavior() -> Behavior:
    """Behavior spec: fires when a claim is created, checks for evidence."""
    return Behavior(
        name="evidence_check",
        matcher=EventMatcher(event_types=("claim.created",)),
        kind=BehaviorKind.EVENT,
        description="Detects claims without supporting evidence",
    )


def evidence_check_handler_factory(
    patch_applier: Any,
) -> BehaviorHandler:
    """Create a handler that proposes patches for claims without evidence.

    Args:
        patch_applier: PatchApplier to propose patches through.

    Returns:
        A BehaviorHandler that checks the graph for evidence and proposes
        a patch if none is found.
    """
    def handler(ctx: BehaviorContext) -> None:
        claim_id = ctx.event.payload.get("claim_id", "")
        if not claim_id:
            return

        # Check graph snapshot for evidence linked to this claim.
        graph = ctx.graph_snapshot or {}
        has_evidence = any(
            v.get("type") == "evidence" and v.get("claim_id") == claim_id
            for v in graph.values()
        )

        if not has_evidence:
            # Propose a patch to flag the claim as needing evidence.
            patch_applier.propose(
                proposed_by="evidence_check",
                patch={"op_type": "update_claim_status",
                       "payload": {"claim_id": claim_id, "new_status": "needs_evidence"}},
                reason="Claim created without supporting evidence — measurable improvement needed",
            )

    return handler


# ── Contradiction Detector ─────────────────────────────────────────────────


def contradiction_detector_behavior() -> Behavior:
    """Behavior spec: fires on claim.created, detects contradictions."""
    return Behavior(
        name="contradiction_detector",
        matcher=EventMatcher(event_types=("claim.created",)),
        kind=BehaviorKind.EVENT,
        activate_after=1,  # Need at least 1 existing claim to contradict
        description="Detects contradictions between claims",
    )


def contradiction_detector_handler_factory(
    patch_applier: Any,
) -> BehaviorHandler:
    """Create a handler that detects contradictions with existing claims."""
    def handler(ctx: BehaviorContext) -> None:
        new_claim_text = ctx.event.payload.get("text", "").lower()
        if not new_claim_text:
            return

        graph = ctx.graph_snapshot or {}
        for vid, vdata in graph.items():
            if vdata.get("type") != "claim":
                continue
            existing_text = vdata.get("text", "").lower()
            # Simple contradiction heuristic: negation words.
            negations = ["not", "no", "never", "false", "incorrect"]
            for neg in negations:
                if (neg in new_claim_text and neg not in existing_text
                        and existing_text
                        and existing_text in new_claim_text.replace(neg, "").strip()):
                    patch_applier.propose(
                        proposed_by="contradiction_detector",
                        patch={"op_type": "add_edge",
                               "payload": {"source": ctx.event.payload.get("claim_id", ""),
                                           "target": vid, "kind": "contradicts"}},
                        reason="Detected contradiction between claims — measurable improvement",
                    )
                    break

    return handler


# ── Gap Filler ────────────────────────────────────────────────────────────


def gap_filler_behavior() -> Behavior:
    """Behavior spec: fires on gap.detected, proposes a patch to fill it."""
    return Behavior(
        name="gap_filler",
        matcher=EventMatcher(event_types=("gap.detected",)),
        kind=BehaviorKind.EVENT,
        description="Proposes patches to fill detected gaps",
    )


def gap_filler_handler_factory(
    patch_applier: Any,
) -> BehaviorHandler:
    """Create a handler that proposes patches to fill gaps."""
    def handler(ctx: BehaviorContext) -> None:
        gap_type = ctx.event.payload.get("gap_type", "")
        gap_location = ctx.event.payload.get("location", "")

        if not gap_type:
            return

        # Propose a patch to fill the gap.
        patch_applier.propose(
            proposed_by="gap_filler",
            patch={"op_type": "add_node",
                   "payload": {"node_id": f"fill-{gap_location or gap_type}",
                               "kind": "filler", "text": f"Fills {gap_type} gap"}},
            reason="Fills detected gap — measurable improvement",
        )

    return handler


# ── Preset registry ────────────────────────────────────────────────────────


PRESET_BEHAVIORS = {
    "evidence_check": (evidence_check_behavior, evidence_check_handler_factory),
    "contradiction_detector": (contradiction_detector_behavior, contradiction_detector_handler_factory),
    "gap_filler": (gap_filler_behavior, gap_filler_handler_factory),
}


def get_preset(name: str, patch_applier: Any) -> tuple[Behavior, BehaviorHandler]:
    """Get a preset behavior + handler by name.

    Args:
        name: preset name (evidence_check, contradiction_detector, gap_filler).
        patch_applier: PatchApplier for the handler to propose patches through.

    Returns:
        Tuple of (Behavior spec, handler function).

    Raises:
        KeyError: if the preset name is not found.
    """
    if name not in PRESET_BEHAVIORS:
        raise KeyError(f"Unknown preset: {name}. Available: {list(PRESET_BEHAVIORS.keys())}")
    behavior_fn, handler_fn = PRESET_BEHAVIORS[name]
    return behavior_fn(), handler_fn(patch_applier)


def list_presets() -> list[str]:
    """List available preset names."""
    return list(PRESET_BEHAVIORS.keys())
