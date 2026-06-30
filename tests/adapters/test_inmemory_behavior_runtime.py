"""Tests for M053 S02 — InMemoryBehaviorRuntime (reactive engine)."""

from __future__ import annotations

import pytest

from active_skill_system.adapters.inmemory_behavior_runtime import InMemoryBehaviorRuntime
from active_skill_system.application.ports.behavior_runtime import (
    BehaviorRuntime,
)
from active_skill_system.domain.behavior import Behavior, EventMatcher
from active_skill_system.domain.graph_primitives import GraphEvent


def _make_event(event_type: str = "test.event", payload: dict | None = None,
                eid: str = "evt-001") -> GraphEvent:
    return GraphEvent(
        id=eid, type=event_type, payload=payload or {},
        actor="test", run_id="run-1", timestamp_ns=1,
    )


# ── Protocol conformance ───────────────────────────────────────────────────


def test_inmemory_behavior_runtime_satisfies_protocol() -> None:
    rt = InMemoryBehaviorRuntime()
    assert isinstance(rt, BehaviorRuntime)


# ── Registration ───────────────────────────────────────────────────────────


def test_register_adds_behavior() -> None:
    rt = InMemoryBehaviorRuntime()
    b = Behavior(name="test", matcher=EventMatcher(event_types=("evt",)))
    rt.register(b, lambda ctx: None)
    assert len(rt.list_registrations()) == 1


def test_register_rejects_non_behavior() -> None:
    rt = InMemoryBehaviorRuntime()
    with pytest.raises(TypeError, match="behavior must be a Behavior"):
        rt.register("not-a-behavior", lambda ctx: None)  # type: ignore[arg-type]


def test_register_rejects_non_callable_handler() -> None:
    rt = InMemoryBehaviorRuntime()
    b = Behavior(name="test", matcher=EventMatcher(event_types=("evt",)))
    with pytest.raises(TypeError, match="handler must be callable"):
        rt.register(b, "not-callable")  # type: ignore[arg-type]


# ── Dispatch ──────────────────────────────────────────────────────────────


def test_publish_fires_matching_behavior() -> None:
    rt = InMemoryBehaviorRuntime()
    fired: list[str] = []

    b = Behavior(name="logger", matcher=EventMatcher(event_types=("claim.created",)))
    rt.register(b, lambda ctx: fired.append(ctx.event.type))

    rt.publish(_make_event("claim.created"))
    assert fired == ["claim.created"]
    assert rt.list_registrations()[0].fire_count == 1


def test_publish_does_not_fire_non_matching_behavior() -> None:
    rt = InMemoryBehaviorRuntime()
    fired: list[str] = []

    b = Behavior(name="logger", matcher=EventMatcher(event_types=("claim.created",)))
    rt.register(b, lambda ctx: fired.append(ctx.event.type))

    rt.publish(_make_event("other.event"))
    assert fired == []
    assert rt.list_registrations()[0].fire_count == 0


def test_publish_fires_multiple_matching_behaviors() -> None:
    rt = InMemoryBehaviorRuntime()
    fired: list[str] = []

    rt.register(
        Behavior(name="a", matcher=EventMatcher(event_types=("evt",))),
        lambda ctx: fired.append("a"),
    )
    rt.register(
        Behavior(name="b", matcher=EventMatcher(event_types=("evt",))),
        lambda ctx: fired.append("b"),
    )

    rt.publish(_make_event("evt"))
    assert sorted(fired) == ["a", "b"]


def test_publish_respects_payload_filter() -> None:
    rt = InMemoryBehaviorRuntime()
    fired: list[str] = []

    b = Behavior(name="high_alert", matcher=EventMatcher(
        event_types=("alert",), payload_filter={"severity": "high"},
    ))
    rt.register(b, lambda ctx: fired.append(ctx.event.type))

    rt.publish(_make_event("alert", {"severity": "low"}))
    rt.publish(_make_event("alert", {"severity": "high"}))
    assert fired == ["alert"]
    assert rt.list_registrations()[0].fire_count == 1


# ── Error handling ─────────────────────────────────────────────────────────


def test_handler_exception_does_not_crash_runtime() -> None:
    rt = InMemoryBehaviorRuntime()

    def bad_handler(ctx) -> None:  # type: ignore[no-untyped-def]
        raise ValueError("boom")

    rt.register(
        Behavior(name="bad", matcher=EventMatcher(event_types=("evt",))),
        bad_handler,
    )
    rt.register(
        Behavior(name="good", matcher=EventMatcher(event_types=("evt",))),
        lambda ctx: None,
    )

    # Should not raise.
    rt.publish(_make_event("evt"))

    regs = rt.list_registrations()
    bad_reg = [r for r in regs if r.behavior.name == "bad"][0]
    good_reg = [r for r in regs if r.behavior.name == "good"][0]
    assert bad_reg.error_count == 1
    assert "boom" in bad_reg.last_error
    assert good_reg.fire_count == 1


def test_handler_error_logged() -> None:
    rt = InMemoryBehaviorRuntime()
    rt.register(
        Behavior(name="bad", matcher=EventMatcher(event_types=("evt",))),
        lambda ctx: (_ for _ in ()).throw(ValueError("crash")),
    )
    rt.publish(_make_event("evt"))
    assert rt.list_registrations()[0].error_count == 1


# ── Reentrancy (chained reactions) ─────────────────────────────────────────


def test_handler_can_emit_followup_event() -> None:
    rt = InMemoryBehaviorRuntime()
    chain: list[str] = []

    rt.register(
        Behavior(name="first", matcher=EventMatcher(event_types=("start",))),
        lambda ctx: (chain.append("first"), ctx.emit(_make_event("second", eid="evt-2"))),
    )
    rt.register(
        Behavior(name="second", matcher=EventMatcher(event_types=("second",))),
        lambda ctx: chain.append("second"),
    )

    rt.publish(_make_event("start"))
    assert chain == ["first", "second"]


def test_max_depth_prevents_infinite_loop() -> None:
    rt = InMemoryBehaviorRuntime(max_depth=5)
    call_count = [0]

    def recursive_handler(ctx) -> None:  # type: ignore[no-untyped-def]
        call_count[0] += 1
        ctx.emit(_make_event("loop", eid=f"evt-{call_count[0]}"))

    rt.register(
        Behavior(name="loop", matcher=EventMatcher(event_types=("loop", "start",))),
        recursive_handler,
    )

    rt.publish(_make_event("start"))
    # Should have been limited by max_depth, not infinite.
    assert call_count[0] <= 6


# ── activate_after ────────────────────────────────────────────────────────


def test_activate_after_delays_behavior() -> None:
    rt = InMemoryBehaviorRuntime()
    fired: list[int] = []

    rt.register(
        Behavior(name="delayed", matcher=EventMatcher(event_types=("evt",)), activate_after=3),
        lambda ctx: fired.append(ctx.events_processed),
    )

    rt.publish(_make_event("evt"))  # events_processed=1, < 3, no fire
    rt.publish(_make_event("evt"))  # events_processed=2, < 3, no fire
    rt.publish(_make_event("evt"))  # events_processed=3, >= 3, fire!
    assert len(fired) == 1


# ── events_processed tracking ──────────────────────────────────────────────


def test_events_processed_increments() -> None:
    rt = InMemoryBehaviorRuntime()
    assert rt.events_processed == 0
    rt.publish(_make_event("evt"))
    rt.publish(_make_event("evt"))
    assert rt.events_processed == 2
