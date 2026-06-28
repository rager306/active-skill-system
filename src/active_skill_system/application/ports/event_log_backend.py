"""L2 Application — EventLogBackend port (M051 S01, Wave A).

The raw-persistence seam for the event log. This is the dialect layer below
``EventStore``: it speaks row tuples, not ``GraphEvent`` objects.

Adapters:
  - ``SQLiteEventLog`` (stdlib sqlite3) — production default.
  - ``PostgresEventLog`` (psycopg3) — future, when Postgres is needed.
  - ``InMemoryEventLog`` (dict-of-list) — tests.

Swapping SQLite → Postgres is a one-adapter change; ``EventStore`` and
everything above it stay unchanged.

The row contract is fixed: ``(id, run_id, type, payload_json, actor,
caused_by, timestamp_ns)``. Adapters map this to their native schema but
preserve column order so ``EventStore`` can (de)serialise generically.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

# Fixed row contract: (id, run_id, type, payload_json, actor, caused_by, timestamp_ns)
EventRow = tuple[str, str, str, str, str, str, int]


@runtime_checkable
class EventLogBackend(Protocol):
    """Raw append-only event-log persistence.

    Implementations store rows in the fixed ``EventRow`` shape and order
    them by ``timestamp_ns`` (then insertion order for ties).
    """

    def append_row(self, row: EventRow) -> None:
        """Append a single event row. Idempotent on row[0] (the event id)."""
        ...

    def iter_rows(self, run_id: str | None = None) -> Iterator[EventRow]:
        """Iterate rows in (timestamp_ns, insertion) order.

        Args:
            run_id: if given, filter to that run; else all rows.
        """
        ...

    def rows_since(self, event_id: str) -> tuple[EventRow, ...]:
        """Rows strictly AFTER ``event_id`` (exclusive), in order."""
        ...

    def rows_until(self, event_id: str) -> tuple[EventRow, ...]:
        """Rows up to AND INCLUDING ``event_id``, in order."""
        ...

    def count_rows(self) -> int:
        """Total number of stored rows."""
        ...
