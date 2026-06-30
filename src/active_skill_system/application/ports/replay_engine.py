"""L2 Application — ReplayEngine port (M054 S01, Wave D primitive #10).

The replay engine port: reconstruct graph state from an event log. Two modes:
  - STRICT: replay events into the graph WITHOUT firing behaviors (pure
    state reconstruction — used for fork prefix replay).
  - PERMISSIVE: replay events AND fire behaviors (as if events are new —
    used for debugging "what would happen if events fired fresh").

Adapters:
  - NativeReplayEngine (S02) — uses EventStore + GraphBackend.
  - ActivegraphReplayAdapter (future) — delegates to activegraph.Runtime.replay.

This port is the swap seam for replay implementations.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from active_skill_system.domain.replay import ReplayResult


@runtime_checkable
class ReplayEngine(Protocol):
    """Reconstruct graph state from an event log.

    Strict mode: replay events into GraphBackend without firing behaviors.
    Permissive mode: replay events AND fire behaviors via BehaviorRuntime.

    The fork-and-diff pipeline uses strict mode for prefix replay (M052 S10),
    so shared prefix events don't re-trigger reactive behavior.
    """

    def replay(self, run_id: str, mode: str = "strict") -> ReplayResult:
        """Replay the event log for a run into a reconstructed graph.

        Args:
            run_id: the run to replay.
            mode: "strict" (no behaviors) or "permissive" (behaviors fire).

        Returns:
            ReplayResult with reconstructed graph state + counts.
        """
        ...
