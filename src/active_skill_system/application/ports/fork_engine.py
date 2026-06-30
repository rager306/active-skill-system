"""L2 Application — ForkEngine port (M052 S09, D020).

The fork-and-diff engine port. Branches any run at any event into an
independent fork, then structurally diffs the fork against the parent.

Adapters:
  - NativeForkEngine — uses EventStore + GraphBackend (no activegraph).
  - ActivegraphForkAdapter — future, delegates to activegraph.Runtime.fork.

The port is the swap seam: if we later want activegraph's fork with LLM
cache replay, we swap the adapter without touching the application layer.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from active_skill_system.domain.fork import Diff, Fork


@runtime_checkable
class ForkEngine(Protocol):
    """Fork-and-diff engine."""

    def fork(
        self,
        parent_run_id: str,
        at_event_id: str,
        config_overrides: dict[str, Any] | None = None,
    ) -> Fork:
        """Branch parent_run_id at at_event_id into a new fork run.

        Copies the parent's event prefix (events up to and including
        at_event_id) into a new run_id. Returns a Fork specification.

        Args:
            parent_run_id: the source run to fork from.
            at_event_id: the event to fork at (inclusive — prefix includes it).
            config_overrides: what changed in the fork (e.g. {"model": "glm"}).
        """
        ...

    def diff(self, parent_run_id: str, fork_run_id: str) -> Diff:
        """Structurally diff two runs.

        Returns a Diff with divergent objects, relations, and the split
        event id (first event where the traces diverge).
        """
        ...
