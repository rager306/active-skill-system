"""Tests for M054 S02 — NativeReplayEngine adapter."""

from __future__ import annotations

import pytest

from active_skill_system.adapters.event_store_impl import EventStoreImpl
from active_skill_system.adapters.inmemory_behavior_runtime import InMemoryBehaviorRuntime
from active_skill_system.adapters.inmemory_event_log import InMemoryEventLog
from active_skill_system.adapters.native_replay_engine import NativeReplayEngine
from active_skill_system.application.ports.replay_engine import ReplayEngine
from active_skill_system.domain.behavior import Behavior, EventMatcher
from active_skill_system.domain.graph_primitives import GraphEvent
from active_skill_system.domain.replay import ReplayMode, ReplayResult


def _make_store_with_events(run_id: str = "run-1") -> EventStoreImpl:
    """Build an EventStore with claim.created + relation.created events."""
    store = EventStoreImpl(InMemoryEventLog())
    store.append(GraphEvent(
        id="e1", type="claim.created",
        payload={"claim_id": "c1", "text": "sky is blue", "type": "claim"},
        actor="test", run_id=run_id, timestamp_ns=1,
    ))
    store.append(GraphEvent(
        id="e2", type="relation.created",
        payload={"kind": "supports", "source": "e1", "target": "c1"},
        actor="test", run_id=run_id, timestamp_ns=2,
    ))
    return store


# ── Construction ──────────────────────────────────────────────────────────


def test_native_replay_engine_satisfies_protocol() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    assert isinstance(NativeReplayEngine(store), ReplayEngine)


def test_native_replay_engine_rejects_none_store() -> None:
    with pytest.raises(TypeError, match="event_store must be a non-None"):
        NativeReplayEngine(None)  # type: ignore[arg-type]


# ── Strict mode ───────────────────────────────────────────────────────────


def test_strict_replay_reconstructs_graph() -> None:
    store = _make_store_with_events()
    engine = NativeReplayEngine(store)
    result = engine.replay("run-1", mode=ReplayMode.STRICT)

    assert isinstance(result, ReplayResult)
    assert result.mode == "strict"
    assert result.events_replayed == 2
    assert result.vertices_reconstructed == 1  # c1
    assert result.edges_reconstructed == 1  # supports edge
    assert result.behaviors_fired == 0  # strict = no behaviors
    assert "c1" in result.graph_snapshot


def test_strict_replay_empty_run() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    engine = NativeReplayEngine(store)
    result = engine.replay("nonexistent", mode="strict")

    assert result.events_replayed == 0
    assert result.vertices_reconstructed == 0
    assert result.behaviors_fired == 0


def test_strict_replay_with_behavior_runtime_no_firing() -> None:
    """Strict mode doesn't fire behaviors even with runtime wired."""
    store = _make_store_with_events()
    runtime = InMemoryBehaviorRuntime()
    runtime.register(
        Behavior(name="test", matcher=EventMatcher(event_types=("claim.created",))),
        lambda ctx: None,
    )
    engine = NativeReplayEngine(store, behavior_runtime=runtime)
    result = engine.replay("run-1", mode="strict")

    assert result.behaviors_fired == 0
    assert runtime.list_registrations()[0].fire_count == 0


# ── Permissive mode ───────────────────────────────────────────────────────


def test_permissive_replay_fires_behaviors() -> None:
    """Permissive mode fires behaviors during replay."""
    store = _make_store_with_events()
    runtime = InMemoryBehaviorRuntime()
    runtime.register(
        Behavior(name="test", matcher=EventMatcher(event_types=("claim.created",))),
        lambda ctx: None,
    )
    engine = NativeReplayEngine(store, behavior_runtime=runtime)
    result = engine.replay("run-1", mode="permissive")

    assert result.behaviors_fired == 1
    assert runtime.list_registrations()[0].fire_count == 1


def test_permissive_without_runtime_no_firing() -> None:
    """Permissive mode without runtime behaves like strict."""
    store = _make_store_with_events()
    engine = NativeReplayEngine(store, behavior_runtime=None)
    result = engine.replay("run-1", mode="permissive")

    assert result.behaviors_fired == 0


# ── Graph reconstruction ──────────────────────────────────────────────────


def test_replay_reconstructs_vertex_from_patch_applied() -> None:
    """patch.applied events add nodes to the reconstructed graph."""
    store = EventStoreImpl(InMemoryEventLog())
    store.append(GraphEvent(
        id="e1", type="patch.applied",
        payload={"patch": {"op_type": "add_node", "payload": {"node_id": "n1", "kind": "filler"}}},
        actor="test", run_id="r1", timestamp_ns=1,
    ))
    engine = NativeReplayEngine(store)
    result = engine.replay("r1", mode="strict")

    assert result.vertices_reconstructed == 1
    assert "n1" in result.graph_snapshot


def test_replay_reconstructs_edge_from_patch_applied() -> None:
    """patch.applied events with add_edge add edges to reconstructed graph."""
    store = EventStoreImpl(InMemoryEventLog())
    store.append(GraphEvent(
        id="e1", type="patch.applied",
        payload={"patch": {"op_type": "add_edge",
                           "payload": {"kind": "supports", "source": "e1", "target": "c1"}}},
        actor="test", run_id="r1", timestamp_ns=1,
    ))
    engine = NativeReplayEngine(store)
    result = engine.replay("r1", mode="strict")

    assert result.edges_reconstructed == 1


# ── Error handling ────────────────────────────────────────────────────────


def test_replay_rejects_bad_mode() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    engine = NativeReplayEngine(store)
    with pytest.raises(ValueError, match="mode must be strict/permissive"):
        engine.replay("r1", mode="invalid")


def test_replay_result_has_duration() -> None:
    store = _make_store_with_events()
    engine = NativeReplayEngine(store)
    result = engine.replay("run-1", mode="strict")

    assert result.duration_ns > 0


def test_replay_result_summary() -> None:
    store = _make_store_with_events()
    engine = NativeReplayEngine(store)
    result = engine.replay("run-1", mode="strict")

    s = result.summary()
    assert "run-1" in s
    assert "strict" in s
    assert "2 events" in s
