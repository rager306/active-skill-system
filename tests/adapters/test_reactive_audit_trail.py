"""Tests for M053 S10 — Reactive audit trail via EventStore."""

from __future__ import annotations

import pytest

from active_skill_system.adapters.event_emitting_behavior_runtime import (
    EventEmittingBehaviorRuntime,
)
from active_skill_system.adapters.event_emitting_patch_applier import (
    EventEmittingPatchApplier,
)
from active_skill_system.adapters.event_store_impl import EventStoreImpl
from active_skill_system.adapters.inmemory_event_log import InMemoryEventLog
from active_skill_system.domain.behavior import Behavior, EventMatcher
from active_skill_system.domain.graph_primitives import GraphEvent


def _make_store() -> EventStoreImpl:
    return EventStoreImpl(InMemoryEventLog())


def _make_event(event_type: str = "test.event", payload: dict | None = None) -> GraphEvent:
    return GraphEvent(
        id="evt-001", type=event_type, payload=payload or {},
        actor="test", run_id="run-1", timestamp_ns=1,
    )


# ── EventEmittingBehaviorRuntime ──────────────────────────────────────────


def test_event_emitting_runtime_rejects_none_store() -> None:
    with pytest.raises(TypeError, match="event_store must be a non-None"):
        EventEmittingBehaviorRuntime(None)  # type: ignore[arg-type]


def test_behavior_trigger_emits_event() -> None:
    """Publishing an event that fires a behavior emits behavior.triggered."""
    store = _make_store()
    rt = EventEmittingBehaviorRuntime(store)
    rt.register(
        Behavior(name="test", matcher=EventMatcher(event_types=("evt",))),
        lambda ctx: None,
    )
    rt.publish(_make_event("evt"))

    triggered = list(store.iter_events())
    types = [e.type for e in triggered]
    assert "behavior.triggered" in types


def test_behavior_failure_emits_event() -> None:
    """A failed behavior handler emits behavior.failed."""
    store = _make_store()
    rt = EventEmittingBehaviorRuntime(store)
    rt.register(
        Behavior(name="bad", matcher=EventMatcher(event_types=("evt",))),
        lambda ctx: (_ for _ in ()).throw(ValueError("crash")),
    )
    rt.publish(_make_event("evt"))

    events = list(store.iter_events())
    types = [e.type for e in events]
    assert "behavior.triggered" in types
    assert "behavior.failed" in types


def test_non_matching_behavior_no_event() -> None:
    """A behavior that doesn't match doesn't emit an event."""
    store = _make_store()
    rt = EventEmittingBehaviorRuntime(store)
    rt.register(
        Behavior(name="test", matcher=EventMatcher(event_types=("other",))),
        lambda ctx: None,
    )
    rt.publish(_make_event("evt"))

    events = list(store.iter_events())
    assert all(e.type != "behavior.triggered" for e in events)


# ── EventEmittingPatchApplier ─────────────────────────────────────────────


def test_event_emitting_applier_rejects_none_store() -> None:
    with pytest.raises(TypeError, match="event_store must be a non-None"):
        EventEmittingPatchApplier(None)  # type: ignore[arg-type]


def test_propose_emits_patch_proposed() -> None:
    store = _make_store()
    applier = EventEmittingPatchApplier(store)
    applier.propose("behavior_x", {"op": "add"})

    events = list(store.iter_events())
    types = [e.type for e in events]
    assert "patch.proposed" in types


def test_approve_emits_policy_approved() -> None:
    store = _make_store()
    applier = EventEmittingPatchApplier(store)
    p = applier.propose("b", {})
    applier.approve(p.id, "policy1")

    events = list(store.iter_events())
    types = [e.type for e in events]
    assert "policy.approved" in types


def test_reject_emits_policy_rejected() -> None:
    store = _make_store()
    applier = EventEmittingPatchApplier(store)
    p = applier.propose("b", {})
    applier.reject(p.id, "policy1")

    events = list(store.iter_events())
    types = [e.type for e in events]
    assert "policy.rejected" in types


def test_apply_emits_patch_applied() -> None:
    store = _make_store()
    applier = EventEmittingPatchApplier(store, apply_fn=lambda p: None)
    p = applier.propose("b", {})
    applier.approve(p.id)
    applier.apply(p.id)

    events = list(store.iter_events())
    types = [e.type for e in events]
    assert "patch.applied" in types


# ── Full reactive audit trail ─────────────────────────────────────────────


def test_full_reactive_chain_emits_all_events() -> None:
    """End-to-end: event → behavior → propose → policy → apply emits 5 event types."""
    store = _make_store()
    rt = EventEmittingBehaviorRuntime(store)
    applier = EventEmittingPatchApplier(store)

    # Register a behavior that proposes a patch.
    from active_skill_system.application.ports.behavior_runtime import BehaviorContext

    def handler(ctx: BehaviorContext) -> None:
        applier.propose("test_behavior", {"op": "add"}, "test reason")

    rt.register(Behavior(name="test", matcher=EventMatcher(event_types=("evt",))), handler)

    # Publish event → behavior fires → proposes patch.
    rt.publish(_make_event("evt"))

    # Approve + apply the proposed patch.
    pending = applier.list_pending()
    assert len(pending) == 1
    applier.approve(pending[0].id, "policy1")
    applier.apply(pending[0].id)

    # Verify all 5 reactive event types were emitted.
    events = list(store.iter_events())
    types = {e.type for e in events}
    assert "behavior.triggered" in types
    assert "patch.proposed" in types
    assert "policy.approved" in types
    assert "patch.applied" in types
