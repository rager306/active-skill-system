"""L4 Composition — reactive operations (M053 S09/S10).

Wires BehaviorRuntime + PatchApplier + PolicyGate + presets into the sandbox.
Demonstrates the full reactive loop: event → behavior → patch → policy → apply.
"""

from __future__ import annotations

from active_skill_system.adapters.inmemory_behavior_runtime import InMemoryBehaviorRuntime
from active_skill_system.adapters.inmemory_patch_applier import InMemoryPatchApplier
from active_skill_system.adapters.inmemory_trace_collector import InMemoryTraceCollector
from active_skill_system.application.behaviors.presets import (
    get_preset,
    list_presets,
)
from active_skill_system.application.use_cases.policy_gate import PolicyGate
from active_skill_system.composition.cli_exit import EX_OK
from active_skill_system.domain.graph_primitives import GraphEvent


def build_reactive_stack(trace: InMemoryTraceCollector | None = None):
    """Build the full reactive stack: Runtime + Applier + Gate + presets.

    Returns:
        Tuple of (runtime, applier, gate) — fully wired.
    """
    applier = InMemoryPatchApplier()
    gate = PolicyGate(applier)
    runtime = InMemoryBehaviorRuntime(trace=trace)

    # Register AUTO_APPROVE policy (for demo purposes).
    from active_skill_system.domain.policy import Policy, PolicyRule
    gate.register(Policy(
        name="auto_approve_all",
        rule=PolicyRule.AUTO_APPROVE,
        description="Auto-approves all patches (demo mode)",
    ))

    # Register all preset behaviors.
    for name in list_presets():
        behavior, handler = get_preset(name, applier)
        runtime.register(behavior, handler)

    return runtime, applier, gate


def run_behavior_demo(event_log_spec: str | None) -> int:
    """Run the reactive behavior demo.

    Creates a claim.created event, publishes it to the BehaviorRuntime,
    lets behaviors fire and propose patches, then evaluates patches via
    PolicyGate. Shows the full reactive loop.
    """
    trace = InMemoryTraceCollector()
    runtime, applier, gate = build_reactive_stack(trace=trace)

    print("=== Reactive Behavior Demo ===", flush=True)
    print(f"Registered behaviors: {[r.behavior.name for r in runtime.list_registrations()]}", flush=True)
    print(f"Registered policies: {[p.name for p in gate.list_policies()]}", flush=True)
    print(flush=True)

    # 1. Publish a claim.created event (no evidence in graph).
    print("--- Step 1: claim.created (no evidence) ---", flush=True)
    event = GraphEvent(
        id="demo-evt-001",
        type="claim.created",
        payload={"claim_id": "demo-claim-1", "text": "This is a test claim"},
        actor="demo",
        run_id="demo-run-1",
        timestamp_ns=1,
    )
    runtime.publish(event)
    print(f"Events processed: {runtime.events_processed}", flush=True)
    for reg in runtime.list_registrations():
        print(f"  behavior {reg.behavior.name}: fired={reg.fire_count}, errors={reg.error_count}", flush=True)
    print(flush=True)

    # 2. Evaluate proposed patches via PolicyGate.
    print("--- Step 2: PolicyGate evaluates patches ---", flush=True)
    pending = applier.list_pending()
    print(f"Pending patches: {len(pending)}", flush=True)
    evaluations = gate.evaluate_all_pending()
    for ev in evaluations:
        print(f"  {ev.patch_id}: {ev.decision.value} by {ev.policy_name} ({ev.reason})", flush=True)
    print(flush=True)

    # 3. Publish a gap.detected event.
    print("--- Step 3: gap.detected ---", flush=True)
    gap_event = GraphEvent(
        id="demo-evt-002",
        type="gap.detected",
        payload={"gap_type": "missing_context", "location": "node-1"},
        actor="demo",
        run_id="demo-run-1",
        timestamp_ns=2,
    )
    runtime.publish(gap_event)
    print(f"Events processed: {runtime.events_processed}", flush=True)
    print(flush=True)

    # 4. Final state.
    print("--- Step 4: Final state ---", flush=True)
    all_proposals = applier.list_all()
    print(f"Total proposals: {len(all_proposals)}", flush=True)
    for p in all_proposals:
        print(f"  {p.id}: status={p.status}, by={p.proposed_by}", flush=True)
    print(flush=True)

    # 5. Trace summary.
    spans = list(trace.iter_spans())
    print(f"--- Trace: {len(spans)} spans ---", flush=True)
    for s in spans[:5]:
        print(f"  {s.operation} [{s.status}]", flush=True)
    if len(spans) > 5:
        print(f"  ... and {len(spans) - 5} more", flush=True)

    return EX_OK
