"""L3 Adapter — SQLiteEventLog (M051 S02, Wave A).

EventLogBackend backed by stdlib ``sqlite3``. The production default for the
event audit trail. Conforms to the fixed EventRow contract:
``(id, run_id, type, payload_json, actor, caused_by, timestamp_ns)``.

Design:
  - Single table ``graph_events`` with the 7 fixed columns.
  - ``id`` is PRIMARY KEY (idempotent append via INSERT OR IGNORE).
  - Ordered by ``timestamp_ns``; ties broken by insertion (rowid).
  - Optional ``run_id`` index for filtered iteration.
  - ``sqlite:///<path>`` URL or bare path accepted; ``:memory:`` works.

Future: a ``PostgresEventLog`` adapter implements the same EventLogBackend
port over psycopg3 — swap is a one-constructor change in composition.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from urllib.parse import urlparse

from active_skill_system.application.ports.event_log_backend import EventRow
from active_skill_system.domain.errors import ToolError


class SQLiteEventLog:
    """EventLogBackend over stdlib sqlite3."""

    def __init__(self, path_or_url: str = ":memory:") -> None:
        self._path = _resolve_sqlite_path(path_or_url)
        try:
            self._conn = sqlite3.connect(self._path)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS graph_events (
                    id           TEXT PRIMARY KEY,
                    run_id       TEXT NOT NULL DEFAULT '',
                    type         TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    actor        TEXT NOT NULL DEFAULT '',
                    caused_by    TEXT NOT NULL DEFAULT '',
                    timestamp_ns INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_graph_events_run_id ON graph_events(run_id)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_graph_events_ts ON graph_events(timestamp_ns)"
            )
            self._conn.commit()
        except sqlite3.Error as e:
            raise ToolError(f"sqlite event log init failed: {e}", phase="event_log") from None

    def append_row(self, row: EventRow) -> None:
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO graph_events "
                "(id, run_id, type, payload_json, actor, caused_by, timestamp_ns) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            self._conn.commit()
        except sqlite3.Error as e:
            raise ToolError(f"append_row failed: {e}", phase="event_log") from None

    def iter_rows(self, run_id: str | None = None) -> Iterator[EventRow]:
        if run_id is None:
            cur = self._conn.execute(
                "SELECT id, run_id, type, payload_json, actor, caused_by, timestamp_ns "
                "FROM graph_events ORDER BY timestamp_ns, rowid"
            )
        else:
            cur = self._conn.execute(
                "SELECT id, run_id, type, payload_json, actor, caused_by, timestamp_ns "
                "FROM graph_events WHERE run_id = ? ORDER BY timestamp_ns, rowid",
                (run_id,),
            )
        for r in cur:
            yield tuple(r)  # type: ignore[misc]

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
        cur = self._conn.execute("SELECT COUNT(*) FROM graph_events")
        return int(cur.fetchone()[0])

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass


def _resolve_sqlite_path(path_or_url: str) -> str:
    """Accept 'sqlite:///path.db', 'sqlite:///:memory:', or bare path."""
    if path_or_url.startswith("sqlite://"):
        parsed = urlparse(path_or_url)
        return parsed.path or ":memory:"
    return path_or_url
