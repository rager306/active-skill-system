"""Tests for M052 S09 — ForkEngine port + NativeForkEngine adapter."""

from __future__ import annotations

import pytest

from active_skill_system.adapters.event_store_impl import EventStoreImpl
from active_skill_system.adapters.inmemory_event_log import InMemoryEventLog
from active_skill_system.adapters.native_fork_engine import NativeForkEngine
from active_skill_system.application.ports.fork_engine import ForkEngine
from active_skill_system.domain.graph_primitives import GraphEvent


def _make_store_with_events() -> EventStoreImpl:
    """Build an EventStore with 3 events in run 'parent'."""
    store = EventStoreImpl(InMemoryEventLog())
    for i, etype in enumerate(["llm.requested", "llm.responded", "behavior.completed"], start=1):
        store.append(GraphEvent(
            id=f"evt-{i:03d}",
            type=etype,
            payload={"step": i},
            actor="test",
            run_id="parent",
            timestamp_ns=i,
        ))
    return store


def test_native_fork_engine_satisfies_protocol() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    assert isinstance(NativeForkEngine(store), ForkEngine)


def test_fork_engine_rejects_none_store() -> None:
    with pytest.raises(TypeError, match="event_store must be a non-None"):
        NativeForkEngine(None)  # type: ignore[arg-type]


def test_fork_copies_prefix_events() -> None:
    store = _make_store_with_events()
    engine = NativeForkEngine(store)
    fork = engine.fork("parent", "evt-002", config_overrides={"model": "glm"})
    assert fork.parent_run_id == "parent"
    assert fork.fork_run_id.startswith("fork-")
    assert fork.at_event_id == "evt-002"
    assert fork.config_overrides == {"model": "glm"}

    # The fork run should have the prefix events (evt-001 + evt-002).
    fork_events = list(store.iter_events(run_id=fork.fork_run_id))
    assert len(fork_events) == 2
    assert [e.type for e in fork_events] == ["llm.requested", "llm.responded"]


def test_fork_at_last_event_copies_all() -> None:
    store = _make_store_with_events()
    engine = NativeForkEngine(store)
    fork = engine.fork("parent", "evt-003")
    fork_events = list(store.iter_events(run_id=fork.fork_run_id))
    assert len(fork_events) == 3


def test_diff_identical_runs() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    # Two runs with same event types/payloads but different IDs.
    for run_id in ("run-a", "run-b"):
        for i, etype in enumerate(["llm.requested", "llm.responded"], start=1):
            store.append(GraphEvent(
                id=f"{run_id}-evt-{i}",
                type=etype,
                payload={"step": i},
                run_id=run_id,
                timestamp_ns=i,
            ))
    engine = NativeForkEngine(store)
    diff = engine.diff("run-a", "run-b")
    # These runs have same types/payloads but different IDs → divergent objects by ID.
    # The split point is at event 1 (IDs differ from the start).
    assert diff.split_event_id != ""
    assert not diff.is_identical  # different event IDs = divergent


def test_diff_finds_split_point() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    # run-a: event 2 has different payload.
    for i in range(1, 4):
        store.append(GraphEvent(
            id=f"a-evt-{i}", type="test", payload={"v": i},
            run_id="a", timestamp_ns=i,
        ))
    for i in range(1, 4):
        payload = {"v": i} if i < 2 else {"v": i * 10}
        store.append(GraphEvent(
            id=f"b-evt-{i}", type="test", payload=payload,
            run_id="b", timestamp_ns=i,
        ))
    engine = NativeForkEngine(store)
    diff = engine.diff("a", "b")
    assert diff.split_event_id != ""
    assert not diff.is_identical


def test_diff_detects_added_events() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    # run-b has an extra event.
    for i in range(1, 3):
        store.append(GraphEvent(id=f"a-{i}", type="t", payload={}, run_id="a", timestamp_ns=i))
    for i in range(1, 4):
        store.append(GraphEvent(id=f"b-{i}", type="t", payload={}, run_id="b", timestamp_ns=i))
    engine = NativeForkEngine(store)
    diff = engine.diff("a", "b")
    added = [o for o in diff.divergent_objects if o.change_type == "added"]
    assert len(added) >= 1


def test_diff_summary() -> None:
    store = _make_store_with_events()
    engine = NativeForkEngine(store)
    fork = engine.fork("parent", "evt-002")
    diff = engine.diff("parent", fork.fork_run_id)
    s = diff.summary()
    assert "parent" in s
    assert fork.fork_run_id in s
