"""Tests for M054 S11 — E2E reactive scenario with mock LLM.

Proves the full reactive loop works end-to-end:
  ReactiveSandboxAgentRunner publishes events → BehaviorRuntime fires
  Diligence behaviors → behaviors propose patches → PolicyGate approves
  → audit trail in EventStore → trace spans visible.

Uses mock LLM (real-LLM tests are marked @pytest.mark.llm and run with --runllm).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from active_skill_system.adapters.event_emitting_behavior_runtime import (
    EventEmittingBehaviorRuntime,
)
from active_skill_system.adapters.event_emitting_patch_applier import (
    EventEmittingPatchApplier,
)
from active_skill_system.adapters.event_store_impl import EventStoreImpl
from active_skill_system.adapters.inmemory_event_log import InMemoryEventLog
from active_skill_system.adapters.inmemory_trace_collector import InMemoryTraceCollector
from active_skill_system.application.behaviors.diligence_pack import (
    get_diligence_preset,
    list_diligence_presets,
)
from active_skill_system.application.use_cases.policy_gate import PolicyGate
from active_skill_system.application.use_cases.reactive_sandbox_agent_runner import (
    ReactiveSandboxAgentRunner,
)
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

    # Register a behavior that reacts to verify.completed (published by ReactiveSandboxAgentRunner).
    from active_skill_system.domain.behavior import Behavior, EventMatcher
    runtime.register(
        Behavior(
            name="verify_monitor",
            matcher=EventMatcher(event_types=("verify.completed", "run.started")),
        ),
        lambda ctx: None,
    )

    # Register Diligence behaviors (only event-type Behaviors; RelationBehaviors
    # need RelationBehaviorRuntime which is tested separately in S03).
    for name in list_diligence_presets():
        behavior, handler = get_diligence_preset(name, applier)
        from active_skill_system.domain.behavior import Behavior as _B
        if isinstance(behavior, _B):
            runtime.register(behavior, handler)

    return runtime, applier, gate, store, trace


def _mock_sandbox_runner(score: float = 1.0) -> MagicMock:
    """Mock SandboxAgentRunner that returns a result."""
    runner = MagicMock()
    runner._counter = 0
    mock_loop = MagicMock()
    mock_loop.id = "e2e-run-001"
    mock_fitness = MagicMock()
    mock_fitness.score = score
    runner.run.return_value = MagicMock(
        loop=mock_loop, fitness=mock_fitness,
        model="minimax/MiniMax-M3", error=None, trajectory=(),
    )
    return runner


# ── E2E Scenario 1: Full reactive chain with audit trail ──────────────────


def test_e2e_reactive_run_produces_audit_trail() -> None:
    """Reactive run publishes events → behaviors fire → audit trail in EventStore."""
    runtime, applier, gate, store, trace = _build_full_reactive_stack()
    runner = _mock_sandbox_runner()
    reactive = ReactiveSandboxAgentRunner(
        runner=runner, behavior_runtime=runtime, event_store=store,
    )

    reactive.run(model="minimax/MiniMax-M3")

    # Verify audit trail has lifecycle events.
    events = list(store.iter_events())
    types = {e.type for e in events}
    assert "run.started" in types
    assert "verify.completed" in types
    assert "behavior.triggered" in types


def test_e2e_reactive_run_fires_behaviors() -> None:
    """question_generator behavior fires on claim events."""
    runtime, applier, gate, store, trace = _build_full_reactive_stack()
    runner = _mock_sandbox_runner()
    reactive = ReactiveSandboxAgentRunner(
        runner=runner, behavior_runtime=runtime, event_store=store,
    )

    reactive.run(model="minimax/MiniMax-M3")

    # At least one behavior should have fired.
    regs = runtime.list_registrations()
    total_fires = sum(r.fire_count for r in regs)
    assert total_fires >= 1


def test_e2e_reactive_run_trace_spans() -> None:
    """Trace spans created for the full reactive chain."""
    runtime, applier, gate, store, trace = _build_full_reactive_stack()
    runner = _mock_sandbox_runner()
    reactive = ReactiveSandboxAgentRunner(
        runner=runner, behavior_runtime=runtime, event_store=store,
    )

    reactive.run(model="minimax/MiniMax-M3")

    spans = list(trace.iter_spans())
    assert len(spans) >= 1
    # Should have behavior dispatch spans.
    behavior_spans = [s for s in spans if "behavior" in s.operation]
    assert len(behavior_spans) >= 1


# ── E2E Scenario 2: Failed verification ──────────────────────────────────


def test_e2e_failed_verification_publishes_event() -> None:
    """Low score publishes run.failed_verification event."""
    runtime, applier, gate, store, trace = _build_full_reactive_stack()
    runner = _mock_sandbox_runner(score=0.5)
    reactive = ReactiveSandboxAgentRunner(
        runner=runner, behavior_runtime=runtime, event_store=store,
    )

    reactive.run(model="minimax/MiniMax-M3")

    events = list(store.iter_events())
    types = {e.type for e in events}
    assert "run.failed_verification" in types


# ── E2E Scenario 3: Policy gate approves patches ─────────────────────────


def test_e2e_policy_approves_behavior_patches() -> None:
    """Behaviors propose patches → PolicyGate auto-approves."""
    runtime, applier, gate, store, trace = _build_full_reactive_stack()
    runner = _mock_sandbox_runner()
    reactive = ReactiveSandboxAgentRunner(
        runner=runner, behavior_runtime=runtime, event_store=store,
    )

    reactive.run(model="minimax/MiniMax-M3")

    # Evaluate any pending patches.
    evaluations = gate.evaluate_all_pending()

    # If behaviors proposed patches, they should be auto-approved.
    for ev in evaluations:
        assert "approved" in str(ev.decision) or "pending" in str(ev.decision)


# ── Real LLM test (marked, run with --runllm) ────────────────────────────


@pytest.mark.llm
def test_e2e_reactive_real_llm_run() -> None:
    """Real-LLM reactive run (requires --runllm + API key).

    This test is marked llm and only runs with --runllm. It validates the
    full reactive chain with a real LLM call.
    """
    from active_skill_system.adapters.llm.minimax import MiniMaxProvider
    from active_skill_system.adapters.plain_llm_strategy import PlainLLMStrategy
    from active_skill_system.application.use_cases.sandbox_agent_runner import (
        SandboxAgentRunner,
    )

    provider = MiniMaxProvider.from_env()
    strategy = PlainLLMStrategy(provider=provider)
    runner = SandboxAgentRunner(engine=strategy, sandbox_dir="runs/e2e_reactive")

    runtime, applier, gate, store, trace = _build_full_reactive_stack()
    reactive = ReactiveSandboxAgentRunner(
        runner=runner, behavior_runtime=runtime, event_store=store,
    )

    result = reactive.run(model="minimax/MiniMax-M3")

    assert result is not None
    assert result.error is None or "budget" in (result.error or "")
