"""L2 Application — EventStoreImpl (M051 S02, Wave A).

Implements the ``EventStore`` port by (de)serialising ``GraphEvent`` objects
to/from the fixed ``EventRow`` contract and delegating to an
``EventLogBackend``. This is the layer that makes SQLite ↔ Postgres swap a
one-adapter change: EventStoreImpl stays the same; only the injected
EventLogBackend changes.

Pure application (R002): depends only on the EventStore + EventLogBackend
ports and the GraphEvent domain type. No sqlite/postgres imports here.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from active_skill_system.application.ports.event_log_backend import EventLogBackend, EventRow
from active_skill_system.application.ports.event_store import EventStore
from active_skill_system.domain.graph_primitives import GraphEvent


class EventStoreImpl:
    """EventStore backed by an injected EventLogBackend.

    The backend is REQUIRED (R002 — no implicit default). Inject
    SQLiteEventLog for production, InMemoryEventLog for tests, or a future
    PostgresEventLog.
    """

    def __init__(self, backend: EventLogBackend) -> None:
        if backend is None:
            raise TypeError("backend must be a non-None EventLogBackend")
        if not hasattr(backend, "append_row") or not hasattr(backend, "iter_rows"):
            raise TypeError("backend must satisfy EventLogBackend")
        self._backend = backend

    def append(self, event: GraphEvent) -> None:
        self._backend.append_row(_event_to_row(event))

    def iter_events(self, run_id: str | None = None) -> Iterator[GraphEvent]:
        for row in self._backend.iter_rows(run_id):
            yield _row_to_event(row)

    def events_since(self, event_id: str) -> tuple[GraphEvent, ...]:
        return tuple(_row_to_event(r) for r in self._backend.rows_since(event_id))

    def events_until(self, event_id: str) -> tuple[GraphEvent, ...]:
        return tuple(_row_to_event(r) for r in self._backend.rows_until(event_id))


def _event_to_row(event: GraphEvent) -> EventRow:
    return (
        event.id,
        event.run_id,
        event.type,
        json.dumps(event.payload, default=str),
        event.actor,
        event.caused_by,
        event.timestamp_ns,
    )


def _row_to_event(row: EventRow) -> GraphEvent:
    eid, run_id, etype, payload_json, actor, caused_by, ts = row
    try:
        payload = json.loads(payload_json) if payload_json else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return GraphEvent(
        id=eid,
        type=etype,
        payload=payload,
        actor=actor,
        run_id=run_id,
        caused_by=caused_by,
        timestamp_ns=ts,
    )


# EventStoreImpl structurally satisfies EventStore.
_: EventStore = EventStoreImpl(backend=None) if False else None  # type: ignore[assignment]
