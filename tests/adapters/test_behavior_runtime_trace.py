"""Tests for M053 S06 — BehaviorRuntime trace instrumentation."""

from __future__ import annotations

from active_skill_system.adapters.inmemory_behavior_runtime import InMemoryBehaviorRuntime
from active_skill_system.adapters.inmemory_trace_collector import InMemoryTraceCollector
from active_skill_system.domain.behavior import Behavior, EventMatcher
from active_skill_system.domain.graph_primitives import GraphEvent


def _make_event(event_type: str = "test.event") -> GraphEvent:
    return GraphEvent(
        id="evt-001", type=event_type, payload={},
        actor="test", run_id="run-1", timestamp_ns=1,
    )


def test_behavior_runtime_accepts_trace_collector() -> None:
    """InMemoryBehaviorRuntime accepts optional trace= param."""
    trace = InMemoryTraceCollector()
    rt = InMemoryBehaviorRuntime(trace=trace)
    assert rt._trace is trace


def test_publish_with_trace_starts_span() -> None:
    """Publishing an event with trace creates a span for the behavior."""
    trace = InMemoryTraceCollector()
    rt = InMemoryBehaviorRuntime(trace=trace)
    rt.register(
        Behavior(name="test_behavior", matcher=EventMatcher(event_types=("evt",))),
        lambda ctx: None,
    )
    rt.publish(_make_event("evt"))
    spans = list(trace.iter_spans())
    assert len(spans) == 1
    assert "behavior.test_behavior" in spans[0].operation


def test_trace_span_has_behavior_attributes() -> None:
    """Span attributes include event_type and behavior_kind."""
    trace = InMemoryTraceCollector()
    rt = InMemoryBehaviorRuntime(trace=trace)
    rt.register(
        Behavior(name="my_behavior", matcher=EventMatcher(event_types=("evt",))),
        lambda ctx: None,
    )
    rt.publish(_make_event("evt"))
    spans = list(trace.iter_spans())
    assert spans[0].attributes.get("behavior_kind") == "event"
    assert spans[0].attributes.get("event_type") == "evt"


def test_handler_error_span_has_error_status() -> None:
    """Failed behavior dispatch gets status=error in trace."""
    trace = InMemoryTraceCollector()
    rt = InMemoryBehaviorRuntime(trace=trace)
    rt.register(
        Behavior(name="bad_behavior", matcher=EventMatcher(event_types=("evt",))),
        lambda ctx: (_ for _ in ()).throw(ValueError("crash")),
    )
    rt.publish(_make_event("evt"))
    spans = list(trace.iter_spans())
    assert len(spans) == 1
    assert spans[0].status == "error"
    assert "crash" in spans[0].attributes.get("error", "")


def test_multiple_behaviors_get_multiple_spans() -> None:
    """Each behavior dispatch gets its own span."""
    trace = InMemoryTraceCollector()
    rt = InMemoryBehaviorRuntime(trace=trace)
    rt.register(
        Behavior(name="a", matcher=EventMatcher(event_types=("evt",))),
        lambda ctx: None,
    )
    rt.register(
        Behavior(name="b", matcher=EventMatcher(event_types=("evt",))),
        lambda ctx: None,
    )
    rt.publish(_make_event("evt"))
    spans = list(trace.iter_spans())
    assert len(spans) == 2
    ops = {s.operation for s in spans}
    assert "behavior.a" in ops
    assert "behavior.b" in ops


def test_no_trace_no_spans() -> None:
    """Without trace collector, no spans are created (no error)."""
    rt = InMemoryBehaviorRuntime()
    rt.register(
        Behavior(name="test", matcher=EventMatcher(event_types=("evt",))),
        lambda ctx: None,
    )
    rt.publish(_make_event("evt"))
    # Should not crash, should fire the behavior.
    assert rt.list_registrations()[0].fire_count == 1


def test_chained_reactions_get_parent_spans() -> None:
    """Follow-up events from handlers get their own spans (chain visible)."""
    trace = InMemoryTraceCollector()
    rt = InMemoryBehaviorRuntime(trace=trace)

    rt.register(
        Behavior(name="first", matcher=EventMatcher(event_types=("start",))),
        lambda ctx: ctx.emit(_make_event("second")),
    )
    rt.register(
        Behavior(name="second", matcher=EventMatcher(event_types=("second",))),
        lambda ctx: None,
    )

    rt.publish(_make_event("start"))
    spans = list(trace.iter_spans())
    assert len(spans) == 2
    ops = {s.operation for s in spans}
    assert "behavior.first" in ops
    assert "behavior.second" in ops
