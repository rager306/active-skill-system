"""Tests for M054 S07 — ReactiveSandboxAgentRunner."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from active_skill_system.adapters.event_store_impl import EventStoreImpl
from active_skill_system.adapters.inmemory_behavior_runtime import InMemoryBehaviorRuntime
from active_skill_system.adapters.inmemory_event_log import InMemoryEventLog
from active_skill_system.application.use_cases.reactive_sandbox_agent_runner import (
    ReactiveSandboxAgentRunner,
)
from active_skill_system.domain.behavior import Behavior, EventMatcher


def _mock_runner(result_score: float = 1.0) -> MagicMock:
    """Create a mock SandboxAgentRunner that returns a successful result."""
    runner = MagicMock()
    runner._counter = 0

    mock_loop = MagicMock()
    mock_loop.id = "test-run-001"

    mock_fitness = MagicMock()
    mock_fitness.score = result_score

    runner.run.return_value = MagicMock(
        loop=mock_loop,
        fitness=mock_fitness,
        model="minimax/MiniMax-M3",
        error=None,
        trajectory=(),
    )
    return runner


# ── Construction ──────────────────────────────────────────────────────────


def test_reactive_runner_rejects_none_runner() -> None:
    with pytest.raises(TypeError, match="runner must be a non-None"):
        ReactiveSandboxAgentRunner(
            runner=None,  # type: ignore[arg-type]
            behavior_runtime=InMemoryBehaviorRuntime(),
        )


def test_reactive_runner_rejects_none_runtime() -> None:
    with pytest.raises(TypeError, match="behavior_runtime must be a non-None"):
        ReactiveSandboxAgentRunner(
            runner=_mock_runner(),
            behavior_runtime=None,  # type: ignore[arg-type]
        )


# ── Event publishing ──────────────────────────────────────────────────────


def test_run_publishes_lifecycle_events() -> None:
    """run() publishes run.started and verify.completed events."""
    runtime = InMemoryBehaviorRuntime()
    fired_events: list[str] = []
    runtime.register(
        Behavior(name="tracker", matcher=EventMatcher(event_types=(
            "run.started", "verify.completed", "run.succeeded",
        ))),
        lambda ctx: fired_events.append(ctx.event.type),
    )

    runner = _mock_runner()
    reactive = ReactiveSandboxAgentRunner(runner=runner, behavior_runtime=runtime)
    reactive.run(model="minimax/MiniMax-M3")

    assert "run.started" in fired_events
    assert "verify.completed" in fired_events
    assert "run.succeeded" in fired_events


def test_run_publishes_failed_verification_on_low_score() -> None:
    """Score < 1.0 publishes run.failed_verification instead of run.succeeded."""
    runtime = InMemoryBehaviorRuntime()
    fired_events: list[str] = []
    runtime.register(
        Behavior(name="tracker", matcher=EventMatcher(event_types=(
            "run.failed_verification", "run.succeeded",
        ))),
        lambda ctx: fired_events.append(ctx.event.type),
    )

    runner = _mock_runner(result_score=0.5)
    reactive = ReactiveSandboxAgentRunner(runner=runner, behavior_runtime=runtime)
    reactive.run(model="minimax/MiniMax-M3")

    assert "run.failed_verification" in fired_events
    assert "run.succeeded" not in fired_events


# ── EventStore audit trail ────────────────────────────────────────────────


def test_run_persists_events_to_store() -> None:
    """Events are persisted to EventStore for audit trail."""
    store = EventStoreImpl(InMemoryEventLog())
    runtime = InMemoryBehaviorRuntime()
    runner = _mock_runner()

    reactive = ReactiveSandboxAgentRunner(
        runner=runner, behavior_runtime=runtime, event_store=store,
    )
    reactive.run(model="minimax/MiniMax-M3")

    events = list(store.iter_events())
    types = {e.type for e in events}
    assert "run.started" in types
    assert "verify.completed" in types


def test_run_without_store_still_works() -> None:
    """Running without event_store doesn't error."""
    runtime = InMemoryBehaviorRuntime()
    runner = _mock_runner()
    reactive = ReactiveSandboxAgentRunner(runner=runner, behavior_runtime=runtime)
    result = reactive.run(model="minimax/MiniMax-M3")
    assert result is not None


# ── Behavior firing ───────────────────────────────────────────────────────


def test_behaviors_fire_on_run_events() -> None:
    """Registered behaviors fire when lifecycle events are published."""
    runtime = InMemoryBehaviorRuntime()
    fire_count = [0]
    runtime.register(
        Behavior(name="reactive_monitor", matcher=EventMatcher(event_types=("run.started",))),
        lambda ctx: fire_count.__setitem__(0, fire_count[0] + 1),
    )

    runner = _mock_runner()
    reactive = ReactiveSandboxAgentRunner(runner=runner, behavior_runtime=runtime)
    reactive.run(model="minimax/MiniMax-M3")

    assert fire_count[0] == 1


def test_run_propagates_runner_exceptions() -> None:
    """Exceptions from the underlying runner are propagated."""
    runtime = InMemoryBehaviorRuntime()
    runner = _mock_runner()
    runner.run.side_effect = RuntimeError("LLM failed")

    reactive = ReactiveSandboxAgentRunner(runner=runner, behavior_runtime=runtime)
    with pytest.raises(RuntimeError, match="LLM failed"):
        reactive.run(model="minimax/MiniMax-M3")


def test_run_failure_publishes_run_failed_event() -> None:
    """When the runner raises, run.failed event is published before re-raising."""
    runtime = InMemoryBehaviorRuntime()
    fired_events: list[str] = []
    runtime.register(
        Behavior(name="error_tracker", matcher=EventMatcher(event_types=("run.failed",))),
        lambda ctx: fired_events.append(ctx.event.type),
    )

    runner = _mock_runner()
    runner.run.side_effect = RuntimeError("LLM failed")

    reactive = ReactiveSandboxAgentRunner(runner=runner, behavior_runtime=runtime)
    with pytest.raises(RuntimeError):
        reactive.run(model="minimax/MiniMax-M3")

    assert "run.failed" in fired_events


# ── Frame budget ──────────────────────────────────────────────────────────


def test_exhausted_frame_prevents_run() -> None:
    """When frame budget is exhausted, run doesn't proceed."""
    from active_skill_system.domain.reactive_frame import FrameBudget, ReactiveFrame

    budget = FrameBudget(max_llm_calls=1)
    budget.record_llm_call()  # exhaust

    frame = ReactiveFrame(goal="test", budget=budget)
    runtime = InMemoryBehaviorRuntime()
    runner = _mock_runner()

    reactive = ReactiveSandboxAgentRunner(
        runner=runner, behavior_runtime=runtime, reactive_frame=frame,
    )
    result = reactive.run(model="minimax/MiniMax-M3")

    assert "budget exhausted" in (result.error or "")
    # Underlying runner should NOT have been called.
    runner.run.assert_not_called()
