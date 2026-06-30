"""Tests for M053 S01 — BehaviorRuntime port + BehaviorContext."""

from __future__ import annotations

from active_skill_system.application.ports.behavior_runtime import (
    BehaviorContext,
    BehaviorRegistration,
    BehaviorRuntime,
)
from active_skill_system.domain.behavior import Behavior, EventMatcher
from active_skill_system.domain.graph_primitives import GraphEvent


def _make_event(event_type: str = "test.event", payload: dict | None = None) -> GraphEvent:
    return GraphEvent(
        id="evt-001",
        type=event_type,
        payload=payload or {},
        actor="test",
        run_id="run-1",
        timestamp_ns=1,
    )


# ── BehaviorContext ────────────────────────────────────────────────────────


def test_behavior_context_creation() -> None:
    event = _make_event()
    ctx = BehaviorContext(event=event)
    assert ctx.event is event
    assert ctx.graph_snapshot is None
    assert ctx.emit is None
    assert ctx.run_id == ""
    assert ctx.events_processed == 0


def test_behavior_context_with_emit() -> None:
    emitted: list[GraphEvent] = []
    event = _make_event()

    def emit(e: GraphEvent) -> None:
        emitted.append(e)

    ctx = BehaviorContext(event=event, emit=emit, run_id="run-1", events_processed=5)
    assert ctx.run_id == "run-1"
    assert ctx.events_processed == 5
    assert ctx.emit is not None
    ctx.emit(event)
    assert len(emitted) == 1


# ── BehaviorRegistration ───────────────────────────────────────────────────


def test_behavior_registration_defaults() -> None:
    b = Behavior(name="test", matcher=EventMatcher(event_types=("evt",)))
    reg = BehaviorRegistration(behavior=b, handler=lambda ctx: None)
    assert reg.fire_count == 0
    assert reg.error_count == 0
    assert reg.last_error == ""


# ── BehaviorRuntime Protocol ──────────────────────────────────────────────


def test_behavior_runtime_is_protocol() -> None:
    """BehaviorRuntime is a runtime_checkable Protocol."""
    assert hasattr(BehaviorRuntime, "_is_protocol")
    assert hasattr(BehaviorRuntime, "register")
    assert hasattr(BehaviorRuntime, "publish")
    assert hasattr(BehaviorRuntime, "list_registrations")


def test_behavior_runtime_protocol_methods() -> None:
    """Verify method signatures exist on the Protocol."""
    # A minimal implementation should satisfy the Protocol.
    class _FakeRuntime:
        def register(self, behavior, handler):  # type: ignore[no-untyped-def]
            pass

        def publish(self, event):  # type: ignore[no-untyped-def]
            pass

        def list_registrations(self):  # type: ignore[no-untyped-def]
            return []

    fake = _FakeRuntime()
    assert isinstance(fake, BehaviorRuntime)


def test_behavior_context_frozen() -> None:
    """BehaviorContext is a frozen dataclass (immutable)."""
    import pytest

    event = _make_event()
    ctx = BehaviorContext(event=event)
    with pytest.raises((AttributeError, Exception)):  # noqa: B017
        ctx.run_id = "modified"  # type: ignore[misc]
