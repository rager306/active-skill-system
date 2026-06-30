"""Tests for M054 S04 — ReplayEngine trace instrumentation."""

from __future__ import annotations

from active_skill_system.adapters.event_store_impl import EventStoreImpl
from active_skill_system.adapters.inmemory_behavior_runtime import InMemoryBehaviorRuntime
from active_skill_system.adapters.inmemory_event_log import InMemoryEventLog
from active_skill_system.adapters.inmemory_trace_collector import InMemoryTraceCollector
from active_skill_system.adapters.native_replay_engine import NativeReplayEngine
from active_skill_system.domain.behavior import Behavior, EventMatcher
from active_skill_system.domain.graph_primitives import GraphEvent
from active_skill_system.domain.replay import ReplayMode


def _make_store_with_events(run_id: str = "run-1") -> EventStoreImpl:
    store = EventStoreImpl(InMemoryEventLog())
    store.append(GraphEvent(
        id="e1", type="claim.created",
        payload={"claim_id": "c1", "type": "claim"},
        actor="test", run_id=run_id, timestamp_ns=1,
    ))
    store.append(GraphEvent(
        id="e2", type="claim.created",
        payload={"claim_id": "c2", "type": "claim"},
        actor="test", run_id=run_id, timestamp_ns=2,
    ))
    return store


def test_replay_engine_accepts_trace() -> None:
    """NativeReplayEngine accepts optional trace parameter."""
    trace = InMemoryTraceCollector()
    store = _make_store_with_events()
    engine = NativeReplayEngine(store, trace=trace)
    assert engine._trace is trace


def test_strict_replay_creates_span() -> None:
    """Strict replay creates a trace span for the replay operation."""
    trace = InMemoryTraceCollector()
    store = _make_store_with_events()
    engine = NativeReplayEngine(store, trace=trace)

    engine.replay("run-1", mode=ReplayMode.STRICT)

    spans = list(trace.iter_spans())
    assert len(spans) >= 1
    # Should have a replay span.
    replay_spans = [s for s in spans if "replay" in s.operation]
    assert len(replay_spans) >= 1
    assert replay_spans[0].attributes.get("mode") == "strict"


def test_permissive_replay_creates_span() -> None:
    """Permissive replay creates a trace span."""
    trace = InMemoryTraceCollector()
    store = _make_store_with_events()
    engine = NativeReplayEngine(store, trace=trace)

    engine.replay("run-1", mode=ReplayMode.PERMISSIVE)

    spans = list(trace.iter_spans())
    replay_spans = [s for s in spans if "replay" in s.operation]
    assert len(replay_spans) >= 1
    assert replay_spans[0].attributes.get("mode") == "permissive"


def test_replay_span_has_event_count() -> None:
    """Replay span attributes include events_replayed count."""
    trace = InMemoryTraceCollector()
    store = _make_store_with_events()
    engine = NativeReplayEngine(store, trace=trace)

    engine.replay("run-1", mode=ReplayMode.STRICT)

    spans = list(trace.iter_spans())
    replay_spans = [s for s in spans if "replay" in s.operation]
    assert replay_spans[0].attributes.get("events_replayed") == 2


def test_permissive_replay_child_spans_for_behaviors() -> None:
    """Permissive replay creates child spans for behavior firings."""
    trace = InMemoryTraceCollector()
    store = _make_store_with_events()
    runtime = InMemoryBehaviorRuntime(trace=trace)
    runtime.register(
        Behavior(name="test_behavior", matcher=EventMatcher(event_types=("claim.created",))),
        lambda ctx: None,
    )
    engine = NativeReplayEngine(store, behavior_runtime=runtime, trace=trace)

    engine.replay("run-1", mode=ReplayMode.PERMISSIVE)

    spans = list(trace.iter_spans())
    # Should have replay span + behavior dispatch spans.
    behavior_spans = [s for s in spans if "behavior" in s.operation]
    assert len(behavior_spans) >= 1


def test_no_trace_no_error() -> None:
    """Without trace, replay works without error."""
    store = _make_store_with_events()
    engine = NativeReplayEngine(store)

    result = engine.replay("run-1", mode=ReplayMode.STRICT)
    assert result.events_replayed == 2
