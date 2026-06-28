"""L2 Application — EventStore port (M051 S01, Wave A).

The semantic event-log port. Speaks ``GraphEvent`` objects (our domain type),
not raw DB rows. The ``EventLogBackend`` port (event_log_backend.py) is the
raw-persistence seam below this one; ``EventStore`` delegates to it.

The split lets us:
  - swap the raw DB (SQLite → Postgres → in-memory) by changing only the
    ``EventLogBackend`` adapter;
  - keep the application layer speaking semantic ``GraphEvent`` objects.

This port is what powers replay + fork in Waves B/C.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from active_skill_system.domain.graph_primitives import GraphEvent


@runtime_checkable
class EventStore(Protocol):
    """Semantic append-only event log.

    Implementations serialize ``GraphEvent`` to whatever the backing
    ``EventLogBackend`` speaks (rows, tuples, JSON) and delegate.
    """

    def append(self, event: GraphEvent) -> None:
        """Append an event to the log. Idempotent on event id."""
        ...

    def iter_events(self, run_id: str | None = None) -> Iterator[GraphEvent]:
        """Iterate events in insertion order.

        Args:
            run_id: if given, only events of that run; else all events.
        """
        ...

    def events_since(self, event_id: str) -> tuple[GraphEvent, ...]:
        """Events strictly AFTER ``event_id`` (exclusive), in order.

        Used by fork: events_since(fork_point) are the "new" events.
        """
        ...

    def events_until(self, event_id: str) -> tuple[GraphEvent, ...]:
        """Events up to AND INCLUDING ``event_id``, in order.

        Used by fork: events_until(fork_point) are the shared prefix.
        """
        ...
