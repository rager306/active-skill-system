"""Tests for M054 S10 — ForkReplayCacheEngine."""

from __future__ import annotations

import pytest

from active_skill_system.adapters.event_store_impl import EventStoreImpl
from active_skill_system.adapters.fork_replay_cache_engine import ForkReplayCacheEngine
from active_skill_system.adapters.inmemory_event_log import InMemoryEventLog
from active_skill_system.adapters.inmemory_llm_cache import InMemoryLLMCache
from active_skill_system.domain.fork import Fork
from active_skill_system.domain.graph_primitives import GraphEvent


def _make_store_with_events(run_id: str = "parent") -> EventStoreImpl:
    store = EventStoreImpl(InMemoryEventLog())
    store.append(GraphEvent(
        id="e1", type="claim.created",
        payload={"claim_id": "c1", "type": "claim"},
        actor="test", run_id=run_id, timestamp_ns=1,
    ))
    store.append(GraphEvent(
        id="e2", type="llm.completed",
        payload={"model": "MiniMax-M3", "prompt": "test", "response": "answer"},
        actor="test", run_id=run_id, timestamp_ns=2,
    ))
    store.append(GraphEvent(
        id="e3", type="verify.completed",
        payload={"score": 1.0},
        actor="test", run_id=run_id, timestamp_ns=3,
    ))
    return store


# ── Construction ──────────────────────────────────────────────────────────


def test_engine_rejects_none_store() -> None:
    with pytest.raises(TypeError, match="event_store must be a non-None"):
        ForkReplayCacheEngine(event_store=None)  # type: ignore[arg-type]


def test_engine_creates_default_fork_and_replay() -> None:
    store = _make_store_with_events()
    engine = ForkReplayCacheEngine(event_store=store)
    assert engine._fork is not None
    assert engine._replay is not None
    assert engine._cache is None


# ── fork_with_replay ──────────────────────────────────────────────────────


def test_fork_with_replay_returns_fork_and_replay_result() -> None:
    store = _make_store_with_events()
    engine = ForkReplayCacheEngine(event_store=store)

    fork, replay_result = engine.fork_with_replay("parent", "e2")

    assert isinstance(fork, Fork)
    assert fork.parent_run_id == "parent"
    assert replay_result.events_replayed >= 1  # prefix events replayed


def test_fork_with_replay_strict_mode() -> None:
    """Replay uses strict mode (no behaviors fire during prefix)."""
    store = _make_store_with_events()
    engine = ForkReplayCacheEngine(event_store=store)

    _, replay_result = engine.fork_with_replay("parent", "e2")

    assert replay_result.mode == "strict"
    assert replay_result.behaviors_fired == 0


def test_fork_with_replay_reconstructs_graph() -> None:
    """Replay reconstructs the graph from prefix events."""
    store = _make_store_with_events()
    engine = ForkReplayCacheEngine(event_store=store)

    _, replay_result = engine.fork_with_replay("parent", "e3")

    # e1 creates a claim vertex.
    assert replay_result.vertices_reconstructed >= 1
    assert "c1" in replay_result.graph_snapshot


# ── diff_with_cache_analysis ──────────────────────────────────────────────


def test_diff_with_cache_analysis_works() -> None:
    store = _make_store_with_events()
    engine = ForkReplayCacheEngine(
        event_store=store,
        llm_cache=InMemoryLLMCache(),
    )

    # Fork first.
    fork, _ = engine.fork_with_replay("parent", "e2")
    # Now diff.
    diff = engine.diff_with_cache_analysis("parent", fork.fork_run_id)

    assert diff.parent_run_id == "parent"
    assert diff.fork_run_id == fork.fork_run_id


def test_diff_without_cache_works() -> None:
    store = _make_store_with_events()
    engine = ForkReplayCacheEngine(event_store=store)

    fork, _ = engine.fork_with_replay("parent", "e2")
    diff = engine.diff_with_cache_analysis("parent", fork.fork_run_id)

    assert diff is not None


# ── populate_cache_from_prefix ────────────────────────────────────────────


def test_populate_cache_from_prefix_caches_llm_calls() -> None:
    store = _make_store_with_events()
    cache = InMemoryLLMCache()
    engine = ForkReplayCacheEngine(event_store=store, llm_cache=cache)

    count = engine.populate_cache_from_prefix("parent", "e3")

    assert count == 1  # one llm.completed event


def test_populate_cache_without_cache_returns_zero() -> None:
    store = _make_store_with_events()
    engine = ForkReplayCacheEngine(event_store=store)

    count = engine.populate_cache_from_prefix("parent", "e3")

    assert count == 0


def test_populate_cache_stops_at_event() -> None:
    """populate_cache_from_prefix stops at the specified event."""
    store = _make_store_with_events()
    cache = InMemoryLLMCache()
    engine = ForkReplayCacheEngine(event_store=store, llm_cache=cache)

    # Stop at e2 (includes the llm.completed event).
    count = engine.populate_cache_from_prefix("parent", "e2")
    assert count == 1

    # Stop at e1 (before the llm.completed event).
    count = engine.populate_cache_from_prefix("parent", "e1")
    assert count == 0


# ── Full fork pipeline ────────────────────────────────────────────────────


def test_full_fork_pipeline() -> None:
    """End-to-end: populate cache → fork with replay → diff."""
    store = _make_store_with_events()
    cache = InMemoryLLMCache()
    engine = ForkReplayCacheEngine(event_store=store, llm_cache=cache)

    # 1. Populate cache from parent prefix.
    cached = engine.populate_cache_from_prefix("parent", "e3")
    assert cached == 1

    # 2. Fork at e2 with replay.
    fork, replay = engine.fork_with_replay("parent", "e2")
    assert fork.fork_run_id.startswith("fork-")
    assert replay.events_replayed >= 1

    # 3. Diff parent vs fork.
    diff = engine.diff_with_cache_analysis("parent", fork.fork_run_id)
    assert diff is not None
