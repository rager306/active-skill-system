"""Tests for M053 S11 — End-to-end reactive scenario.

Proves the full reactive loop works as a whole:
  create claim → EvidenceCheckBehavior fires → detects missing evidence →
  proposes patch → PolicyGate approves → patch applied → audit trail in EventStore.

This validates all Wave C slices work together.
"""

from __future__ import annotations

from active_skill_system.adapters.event_emitting_behavior_runtime import (
    EventEmittingBehaviorRuntime,
)
from active_skill_system.adapters.event_emitting_patch_applier import (
    EventEmittingPatchApplier,
)
from active_skill_system.adapters.event_store_impl import EventStoreImpl
from active_skill_system.adapters.inmemory_event_log import InMemoryEventLog
from active_skill_system.adapters.inmemory_trace_collector import InMemoryTraceCollector
from active_skill_system.application.behaviors.presets import (
    evidence_check_handler_factory,
)
from active_skill_system.application.use_cases.policy_gate import PolicyGate
from active_skill_system.domain.behavior import Behavior, EventMatcher
from active_skill_system.domain.graph_primitives import GraphEvent
from active_skill_system.domain.policy import Policy, PolicyRule


def _build_full_reactive_stack():
    """Build the full reactive stack with EventStore audit trail + trace."""
    store = EventStoreImpl(InMemoryEventLog())
    trace = InMemoryTraceCollector()
    applier = EventEmittingPatchApplier(store)
    gate = PolicyGate(applier)
    runtime = EventEmittingBehaviorRuntime(store, trace=trace)

    # Register AUTO_APPROVE policy.
    gate.register(Policy(
        name="auto_approve",
        rule=PolicyRule.AUTO_APPROVE,
        description="Auto-approves all patches",
    ))

    # Register evidence_check behavior.
    behavior = Behavior(
        name="evidence_check",
        matcher=EventMatcher(event_types=("claim.created",)),
    )
    handler = evidence_check_handler_factory(applier)
    runtime.register(behavior, handler)

    return runtime, applier, gate, store, trace


# ── E2E Scenario 1: Claim without evidence ────────────────────────────────


def test_e2e_claim_without_evidence_full_chain() -> None:
    """Claim.created → evidence_check fires → proposes patch → policy approves → applied."""
    runtime, applier, gate, store, trace = _build_full_reactive_stack()

    # 1. Publish claim.created event (no evidence in graph).
    runtime.publish(GraphEvent(
        id="e2e-001", type="claim.created",
        payload={"claim_id": "claim-1", "text": "sky is blue"},
        actor="e2e-test", run_id="e2e-run-1", timestamp_ns=1,
    ))

    # 2. evidence_check should have fired.
    regs = runtime.list_registrations()
    assert regs[0].fire_count == 1
    assert regs[0].error_count == 0

    # 3. Patch should have been proposed.
    pending = applier.list_pending()
    assert len(pending) == 1
    assert pending[0].proposed_by == "evidence_check"

    # 4. PolicyGate auto-approves.
    evaluations = gate.evaluate_all_pending()
    assert len(evaluations) == 1
    assert evaluations[0].decision.value == "approved"

    # 5. Apply the approved patch.
    approved = [p for p in applier.list_all() if p.status == "approved"]
    assert len(approved) == 1
    result = applier.apply(approved[0].id)
    assert result.status == "applied"

    # 6. Verify audit trail in EventStore.
    events = list(store.iter_events())
    types = {e.type for e in events}
    assert "behavior.triggered" in types
    assert "patch.proposed" in types
    assert "policy.approved" in types
    assert "patch.applied" in types

    # 7. Verify trace spans.
    spans = list(trace.iter_spans())
    assert len(spans) >= 1
    assert any("behavior.evidence_check" in s.operation for s in spans)


# ── E2E Scenario 2: No false positives ────────────────────────────────────


def test_e2e_claim_with_evidence_no_patch() -> None:
    """Claim with evidence in graph → evidence_check fires but proposes no patch."""
    runtime, applier, gate, store, trace = _build_full_reactive_stack()

    # Override handler with a graph that HAS evidence.
    from active_skill_system.application.ports.behavior_runtime import BehaviorContext

    # Clear existing registration and re-register with custom graph check.
    runtime._registrations.clear()
    graph_with_evidence = {"ev1": {"type": "evidence", "claim_id": "claim-1"}}

    def handler_with_graph(ctx: BehaviorContext) -> None:
        # Simulate evidence existing.
        from active_skill_system.application.behaviors.presets import evidence_check_handler_factory
        real_handler = evidence_check_handler_factory(applier)

        # Temporarily set graph_snapshot.
        new_ctx = BehaviorContext(
            event=ctx.event,
            graph_snapshot=graph_with_evidence,
            emit=ctx.emit,
            run_id=ctx.run_id,
            events_processed=ctx.events_processed,
        )
        real_handler(new_ctx)

    runtime.register(
        Behavior(name="evidence_check", matcher=EventMatcher(event_types=("claim.created",))),
        handler_with_graph,
    )

    runtime.publish(GraphEvent(
        id="e2e-002", type="claim.created",
        payload={"claim_id": "claim-1", "text": "sky is blue"},
        actor="e2e-test", run_id="e2e-run-2", timestamp_ns=1,
    ))

    # No patch should be proposed (evidence exists).
    assert len(applier.list_pending()) == 0
    assert len(applier.list_all()) == 0


# ── E2E Scenario 3: Multiple behaviors fire ───────────────────────────────


def test_e2e_multiple_events_fire_multiple_behaviors() -> None:
    """Multiple events trigger multiple behaviors, each proposing patches."""
    runtime, applier, gate, store, trace = _build_full_reactive_stack()

    # Also register gap_filler.
    from active_skill_system.application.behaviors.presets import gap_filler_handler_factory
    runtime.register(
        Behavior(name="gap_filler", matcher=EventMatcher(event_types=("gap.detected",))),
        gap_filler_handler_factory(applier),
    )

    # Publish claim.created.
    runtime.publish(GraphEvent(
        id="e2e-003", type="claim.created",
        payload={"claim_id": "c1", "text": "test"},
        actor="e2e", run_id="e2e-run-3", timestamp_ns=1,
    ))

    # Publish gap.detected.
    runtime.publish(GraphEvent(
        id="e2e-004", type="gap.detected",
        payload={"gap_type": "missing_data"},
        actor="e2e", run_id="e2e-run-3", timestamp_ns=2,
    ))

    # Both behaviors should have fired.
    regs = {r.behavior.name: r for r in runtime.list_registrations()}
    assert regs["evidence_check"].fire_count == 1
    assert regs["gap_filler"].fire_count == 1

    # Two patches proposed.
    assert len(applier.list_pending()) == 2

    # EventStore has audit trail for both.
    events = list(store.iter_events())
    triggered = [e for e in events if e.type == "behavior.triggered"]
    assert len(triggered) == 2


# ── E2E Scenario 4: Error isolation ───────────────────────────────────────


def test_e2e_behavior_error_doesnt_break_others() -> None:
    """A failing behavior doesn't prevent other behaviors from firing."""
    runtime, applier, gate, store, trace = _build_full_reactive_stack()

    # Register a bad behavior that always fails.
    runtime.register(
        Behavior(name="bad_behavior", matcher=EventMatcher(event_types=("claim.created",))),
        lambda ctx: (_ for _ in ()).throw(ValueError("always fails")),
    )

    runtime.publish(GraphEvent(
        id="e2e-005", type="claim.created",
        payload={"claim_id": "c1", "text": "test"},
        actor="e2e", run_id="e2e-run-4", timestamp_ns=1,
    ))

    # evidence_check should still have fired.
    regs = {r.behavior.name: r for r in runtime.list_registrations()}
    assert regs["evidence_check"].fire_count == 1
    assert regs["bad_behavior"].error_count == 1

    # behavior.failed event emitted for bad_behavior.
    events = list(store.iter_events())
    failed = [e for e in events if e.type == "behavior.failed"]
    assert len(failed) == 1
    assert failed[0].payload["behavior_name"] == "bad_behavior"


# ── E2E Scenario 5: Full trace visibility ─────────────────────────────────


def test_e2e_trace_shows_full_reaction_chain() -> None:
    """Trace spans show the complete reaction chain for debugging."""
    runtime, applier, gate, store, trace = _build_full_reactive_stack()

    runtime.publish(GraphEvent(
        id="e2e-006", type="claim.created",
        payload={"claim_id": "c1", "text": "test"},
        actor="e2e", run_id="e2e-run-5", timestamp_ns=1,
    ))

    spans = list(trace.iter_spans())
    assert len(spans) == 1
    span = spans[0]
    assert span.operation == "behavior.evidence_check"
    assert span.status == "ok"
    assert span.attributes.get("event_type") == "claim.created"
    assert span.attributes.get("behavior_kind") == "event"
