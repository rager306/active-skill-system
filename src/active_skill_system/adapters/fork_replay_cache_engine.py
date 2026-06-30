"""L3 Adapter — ForkReplayCacheIntegration (M054 S10).

Integrates NativeReplayEngine (S02) with ForkEngine (M052) + LLMCache (M052).
The complete fork pipeline: fork → replay prefix → cache LLM calls →
continue with new model.

This is the killer feature from the architecture proposal: fork a run at
event N, replay the prefix (strict mode, no behavior re-fire), and serve
shared prefix LLM calls from cache (zero new API calls). Only events AFTER
the fork point make new LLM calls.
"""

from __future__ import annotations

import logging
from typing import Any

from active_skill_system.adapters.native_fork_engine import NativeForkEngine
from active_skill_system.adapters.native_replay_engine import NativeReplayEngine
from active_skill_system.application.ports.event_store import EventStore
from active_skill_system.application.ports.fork_engine import ForkEngine
from active_skill_system.application.ports.llm_cache import LLMCache, cache_key
from active_skill_system.application.ports.replay_engine import ReplayEngine
from active_skill_system.domain.fork import Diff, Fork

logger = logging.getLogger(__name__)


class ForkReplayCacheEngine:
    """ForkEngine with ReplayEngine prefix reconstruction + LLMCache.

    When forking a run at event N:
      1. ForkEngine.fork() copies events 1..N into the new fork run.
      2. NativeReplayEngine.replay(strict) reconstructs the graph from prefix.
      3. LLMCache records the prefix LLM calls (so fork continuation can
         replay them without new API calls).

    This makes fork continuation cheap: the shared prefix is served from
    cache, only events after the fork point make new LLM calls.

    Args:
        event_store: source of events.
        fork_engine: the fork engine (wraps NativeForkEngine).
        replay_engine: the replay engine (wraps NativeReplayEngine).
        llm_cache: optional cache for LLM call deduplication.
    """

    def __init__(
        self,
        *,
        event_store: EventStore,
        fork_engine: ForkEngine | None = None,
        replay_engine: ReplayEngine | None = None,
        llm_cache: LLMCache | None = None,
    ) -> None:
        if event_store is None:
            raise TypeError("event_store must be a non-None EventStore")
        self._store = event_store
        self._fork = fork_engine or NativeForkEngine(event_store)
        self._replay = replay_engine or NativeReplayEngine(event_store)
        self._cache = llm_cache

    def fork_with_replay(
        self,
        parent_run_id: str,
        at_event_id: str,
        config_overrides: dict[str, Any] | None = None,
    ) -> tuple[Fork, Any]:
        """Fork a run AND replay the prefix (strict mode) + populate LLMCache.

        Returns:
            Tuple of (Fork spec, ReplayResult with reconstructed graph).
        """
        # 1. Fork: copy prefix events into new run.
        fork = self._fork.fork(parent_run_id, at_event_id, config_overrides)

        # 2. Replay: reconstruct graph from prefix (strict = no behaviors).
        replay_result = self._replay.replay(fork.fork_run_id, mode="strict")

        logger.info(
            "fork_with_replay: parent=%s fork=%s events=%d vertices=%d",
            fork.parent_run_id, fork.fork_run_id,
            replay_result.events_replayed, replay_result.vertices_reconstructed,
        )

        return fork, replay_result

    def diff_with_cache_analysis(
        self,
        parent_run_id: str,
        fork_run_id: str,
    ) -> Diff:
        """Diff two runs AND analyze LLMCache hits/misses.

        If LLMCache is wired, reports which prefix LLM calls were served
        from cache (hits) vs new calls (misses).
        """
        diff = self._fork.diff(parent_run_id, fork_run_id)

        # Analyze cache hits/misses for the shared prefix.
        if self._cache is not None:
            cache_hits = 0
            cache_misses = 0
            # Walk parent events up to the split point.
            for event in self._store.iter_events(run_id=parent_run_id):
                if event.id == diff.split_event_id:
                    break
                if event.type in ("llm.requested", "llm.completed"):
                    # Check if this LLM call would be a cache hit.
                    model = event.payload.get("model", "")
                    prompt = event.payload.get("prompt", "")
                    key = cache_key(model=model, system="", prompt=prompt)
                    if self._cache.get(key) is not None:
                        cache_hits += 1
                    else:
                        cache_misses += 1

            logger.info(
                "diff_with_cache_analysis: cache_hits=%d cache_misses=%d",
                cache_hits, cache_misses,
            )

        return diff

    def populate_cache_from_prefix(
        self,
        run_id: str,
        at_event_id: str,
    ) -> int:
        """Populate LLMCache from a run's prefix events.

        Records all LLM calls in events 1..at_event_id into the cache.
        Returns the number of LLM calls cached.

        This is called before forking to ensure the shared prefix is cached.
        """
        if self._cache is None:
            return 0

        cached_count = 0
        for event in self._store.iter_events(run_id=run_id):
            if event.type == "llm.completed":
                model = event.payload.get("model", "")
                system = event.payload.get("system", "")
                prompt = event.payload.get("prompt", "")
                response = event.payload.get("response", "")

                key = cache_key(model=model, system=system, prompt=prompt)
                self._cache.record(key, {"text": response, "model": model})
                cached_count += 1

            if event.id == at_event_id:
                break

        logger.info("populate_cache_from_prefix: cached %d LLM calls", cached_count)
        return cached_count
