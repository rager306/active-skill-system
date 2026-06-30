"""Tests for M052 S10 — AsyncForkEngine (async concurrent fork).

Verifies asyncio.to_thread bridging (D019) and concurrent fork/diff operations.
"""

from __future__ import annotations

import asyncio

import pytest

from active_skill_system.adapters.async_fork_engine import AsyncForkEngine
from active_skill_system.adapters.event_store_impl import EventStoreImpl
from active_skill_system.adapters.inmemory_event_log import InMemoryEventLog
from active_skill_system.domain.fork import Diff, Fork
from active_skill_system.domain.graph_primitives import GraphEvent


def _make_store_with_events(run_id: str = "parent", n_events: int = 3) -> EventStoreImpl:
    """Build an EventStore with N events in the given run."""
    store = EventStoreImpl(InMemoryEventLog())
    types = ["llm.requested", "llm.responded", "behavior.completed", "verify.started", "verify.completed"]
    for i in range(1, n_events + 1):
        store.append(GraphEvent(
            id=f"{run_id}-evt-{i:03d}",
            type=types[i % len(types)],
            payload={"step": i},
            actor="test",
            run_id=run_id,
            timestamp_ns=i,
        ))
    return store


# --- Construction ---


def test_async_fork_engine_rejects_none_store() -> None:
    with pytest.raises(TypeError, match="event_store must be a non-None"):
        AsyncForkEngine(None)  # type: ignore[arg-type]


# --- Async single fork ---


async def test_fork_async_creates_fork() -> None:
    store = _make_store_with_events()
    engine = AsyncForkEngine(store)
    fork = await engine.fork_async("parent", "parent-evt-002")
    assert isinstance(fork, Fork)
    assert fork.parent_run_id == "parent"
    assert fork.fork_run_id.startswith("fork-")


async def test_fork_async_with_overrides() -> None:
    store = _make_store_with_events()
    engine = AsyncForkEngine(store)
    fork = await engine.fork_async("parent", "parent-evt-001", {"model": "glm"})
    assert fork.config_overrides == {"model": "glm"}


# --- Concurrent fork ---


async def test_fork_concurrent_creates_multiple_forks() -> None:
    store = _make_store_with_events()
    engine = AsyncForkEngine(store)
    overrides = [
        {"model": "minimax/MiniMax-M3"},
        {"model": "glm/glm-5.2"},
        {"model": "gemini/gemini-3.1-pro-preview"},
    ]
    forks = await engine.fork_concurrent("parent", "parent-evt-002", overrides)
    assert len(forks) == 3
    assert all(isinstance(f, Fork) for f in forks)
    # Each fork should have different config overrides.
    assert forks[0].config_overrides["model"] == "minimax/MiniMax-M3"
    assert forks[1].config_overrides["model"] == "glm/glm-5.2"
    assert forks[2].config_overrides["model"] == "gemini/gemini-3.1-pro-preview"
    # Each fork should have a unique run_id.
    run_ids = {f.fork_run_id for f in forks}
    assert len(run_ids) == 3


async def test_fork_concurrent_empty_list_returns_empty() -> None:
    store = _make_store_with_events()
    engine = AsyncForkEngine(store)
    forks = await engine.fork_concurrent("parent", "parent-evt-002", [])
    assert forks == []


async def test_fork_concurrent_rejects_non_list() -> None:
    store = _make_store_with_events()
    engine = AsyncForkEngine(store)
    with pytest.raises(TypeError, match="override_list must be a list"):
        await engine.fork_concurrent("parent", "parent-evt-002", "not-a-list")  # type: ignore[arg-type]


async def test_fork_concurrent_all_succeed_simultaneously() -> None:
    """All concurrent forks should succeed and produce unique run IDs.

    This verifies the concurrency contract: asyncio.gather runs all forks
    without serializing them. We check correctness (all succeed, unique IDs)
    rather than timing (which is non-deterministic under GIL + fast in-memory store).
    """
    store = _make_store_with_events(n_events=10)
    engine = AsyncForkEngine(store)
    overrides = [{"model": f"m{i}"} for i in range(8)]

    forks = await engine.fork_concurrent("parent", "parent-evt-005", overrides)

    assert len(forks) == 8
    # All forks succeeded.
    assert all(isinstance(f, Fork) for f in forks)
    # All run_ids unique (no race condition corruption).
    run_ids = [f.fork_run_id for f in forks]
    assert len(set(run_ids)) == 8
    # Each fork copied the prefix.
    for fork in forks:
        events = list(store.iter_events(run_id=fork.fork_run_id))
        assert len(events) == 5


# --- Async diff ---


async def test_diff_async_works() -> None:
    store = _make_store_with_events("run-a", 2)
    for i in range(1, 3):
        store.append(GraphEvent(
            id=f"run-b-evt-{i:03d}", type="test", payload={"step": i * 10},
            run_id="run-b", timestamp_ns=i,
        ))
    engine = AsyncForkEngine(store)
    diff = await engine.diff_async("run-a", "run-b")
    assert isinstance(diff, Diff)
    assert not diff.is_identical


async def test_diff_concurrent_multiple_pairs() -> None:
    store = _make_store_with_events("parent", 3)
    engine = AsyncForkEngine(store)
    # Create 3 forks.
    forks = await engine.fork_concurrent("parent", "parent-evt-002", [
        {"model": "a"}, {"model": "b"}, {"model": "c"},
    ])
    # Diff all 3 forks against parent concurrently.
    pairs = [("parent", f.fork_run_id) for f in forks]
    diffs = await engine.diff_concurrent(pairs)
    assert len(diffs) == 3
    assert all(isinstance(d, Diff) for d in diffs)


async def test_diff_concurrent_empty() -> None:
    store = _make_store_with_events()
    engine = AsyncForkEngine(store)
    diffs = await engine.diff_concurrent([])
    assert diffs == []


async def test_diff_concurrent_rejects_bad_pairs() -> None:
    store = _make_store_with_events()
    engine = AsyncForkEngine(store)
    with pytest.raises(TypeError, match="pairs must be a list"):
        await engine.diff_concurrent("not-a-list")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="each pair must be a 2-tuple"):
        await engine.diff_concurrent([("only-one",)])  # type: ignore[list-item]
