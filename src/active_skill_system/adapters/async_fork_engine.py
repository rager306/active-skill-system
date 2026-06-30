"""L3 Adapter — AsyncForkEngine (M052 S10, D019).

Async wrapper around NativeForkEngine. Enables concurrent fork+run operations
for model comparison scenarios (e.g. fork a run at event N and continue with
3 different models simultaneously).

Per D019: NO retroactive async-ification of existing sync use cases.
asyncio.to_thread bridges sync → async at this seam only.

Usage:
    engine = AsyncForkEngine(store)
    forks = await engine.fork_concurrent("parent", "evt-003", [
        {"model": "minimax/MiniMax-M3"},
        {"model": "glm/glm-5.2"},
        {"model": "gemini/gemini-3.1-pro-preview"},
    ])
    # 3 forks created concurrently (~same wall time as 1 fork)
"""

from __future__ import annotations

import asyncio
from typing import Any

from active_skill_system.adapters.native_fork_engine import NativeForkEngine
from active_skill_system.application.ports.event_store import EventStore
from active_skill_system.domain.fork import Diff, Fork


class AsyncForkEngine:
    """Async ForkEngine wrapping NativeForkEngine with asyncio.to_thread.

    Per D019: this is the ONLY async seam in Wave B. Existing sync use cases
    are NOT modified — they run in thread pool via asyncio.to_thread.
    """

    def __init__(self, event_store: EventStore) -> None:
        if event_store is None:
            raise TypeError("event_store must be a non-None EventStore")
        self._store = event_store
        self._sync_engine = NativeForkEngine(event_store)

    async def fork_async(
        self,
        parent_run_id: str,
        at_event_id: str,
        config_overrides: dict[str, Any] | None = None,
    ) -> Fork:
        """Async fork — delegates sync work to thread pool.

        The EventStore operations are I/O-bound (SQLite, file writes), so
        asyncio.to_thread gives true concurrency without blocking the event loop.
        """
        return await asyncio.to_thread(
            self._sync_engine.fork, parent_run_id, at_event_id, config_overrides
        )

    async def fork_concurrent(
        self,
        parent_run_id: str,
        at_event_id: str,
        override_list: list[dict[str, Any]],
    ) -> list[Fork]:
        """Fork a run into N branches concurrently (one per config override).

        This is the killer use case: fork at event N, continue with M different
        models simultaneously. All forks run in the thread pool concurrently,
        giving ~same wall time as a single fork.

        Args:
            parent_run_id: the source run to fork from.
            at_event_id: the event to fork at (inclusive prefix).
            override_list: list of config overrides, one per fork branch.

        Returns:
            List of Fork specs, one per override_list entry, in order.
        """
        if not override_list:
            return []
        if not isinstance(override_list, list):
            raise TypeError(f"override_list must be a list (got {type(override_list).__name__})")

        tasks = [
            self.fork_async(parent_run_id, at_event_id, overrides)
            for overrides in override_list
        ]
        return await asyncio.gather(*tasks)

    async def diff_async(self, parent_run_id: str, fork_run_id: str) -> Diff:
        """Async diff — delegates sync work to thread pool."""
        return await asyncio.to_thread(
            self._sync_engine.diff, parent_run_id, fork_run_id
        )

    async def diff_concurrent(
        self,
        pairs: list[tuple[str, str]],
    ) -> list[Diff]:
        """Diff N pairs of runs concurrently.

        Useful for comparing all forks against the parent in one shot.

        Args:
            pairs: list of (parent_run_id, fork_run_id) tuples.

        Returns:
            List of Diffs, one per pair, in order.
        """
        if not pairs:
            return []
        if not isinstance(pairs, list):
            raise TypeError(f"pairs must be a list (got {type(pairs).__name__})")
        for pair in pairs:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise TypeError(f"each pair must be a 2-tuple (got {pair!r})")

        tasks = [self.diff_async(parent, fork) for parent, fork in pairs]
        return await asyncio.gather(*tasks)


# AsyncForkEngine structurally satisfies ForkEngine (sync methods inherited
# via _sync_engine delegation pattern). It adds async_* methods on top.
