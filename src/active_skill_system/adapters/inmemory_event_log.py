"""L3 Adapter — InMemoryEventLog (M051 S02, Wave A).

EventLogBackend backed by an in-memory list of rows. Used for tests and
ephemeral runs. Conforms to the fixed EventRow contract:
``(id, run_id, type, payload_json, actor, caused_by, timestamp_ns)``.
"""

from __future__ import annotations

from collections.abc import Iterator

from active_skill_system.application.ports.event_log_backend import EventRow


class InMemoryEventLog:
    """EventLogBackend over a Python list. Thread-unsafe by design (tests)."""

    def __init__(self) -> None:
        self._rows: list[EventRow] = []
        self._ids: set[str] = set()

    def append_row(self, row: EventRow) -> None:
        if row[0] in self._ids:
            return  # idempotent on event id
        self._rows.append(row)
        self._ids.add(row[0])

    def iter_rows(self, run_id: str | None = None) -> Iterator[EventRow]:
        ordered = sorted(self._rows, key=lambda r: (r[6],))
        for r in ordered:
            if run_id is None or r[1] == run_id:
                yield r

    def rows_since(self, event_id: str) -> tuple[EventRow, ...]:
        ordered = list(self.iter_rows())
        for i, r in enumerate(ordered):
            if r[0] == event_id:
                return tuple(ordered[i + 1:])
        return ()

    def rows_until(self, event_id: str) -> tuple[EventRow, ...]:
        ordered = list(self.iter_rows())
        for i, r in enumerate(ordered):
            if r[0] == event_id:
                return tuple(ordered[: i + 1])
        return ()

    def count_rows(self) -> int:
        return len(self._rows)
