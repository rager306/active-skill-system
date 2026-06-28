"""Tests for M051 S02 — EventLogBackend adapters + EventStore delegation."""

from __future__ import annotations

import pytest

from active_skill_system.adapters.event_store_impl import EventStoreImpl
from active_skill_system.adapters.inmemory_event_log import InMemoryEventLog
from active_skill_system.adapters.sqlite_event_log import SQLiteEventLog
from active_skill_system.application.ports.event_log_backend import EventLogBackend
from active_skill_system.application.ports.event_store import EventStore
from active_skill_system.domain.graph_primitives import GraphEvent


def _ev(eid: str, etype: str = "object.created", run_id: str = "r1", ts: int = 0) -> GraphEvent:
    return GraphEvent(
        id=eid, type=etype, payload={"k": "v"}, actor="test",
        run_id=run_id, caused_by="", timestamp_ns=ts,
    )


# ── EventLogBackend Protocol conformance ─────────────────────────────


def test_inmemory_event_log_satisfies_protocol() -> None:
    assert isinstance(InMemoryEventLog(), EventLogBackend)


def test_sqlite_event_log_satisfies_protocol() -> None:
    assert isinstance(SQLiteEventLog(":memory:"), EventLogBackend)


# ── InMemoryEventLog ─────────────────────────────────────────────────


def test_inmemory_append_and_iter() -> None:
    log = InMemoryEventLog()
    log.append_row(("e1", "r1", "object.created", "{}", "a", "", 1))
    log.append_row(("e2", "r1", "behavior.started", "{}", "a", "", 2))
    rows = list(log.iter_rows())
    assert [r[0] for r in rows] == ["e1", "e2"]


def test_inmemory_append_idempotent_on_id() -> None:
    log = InMemoryEventLog()
    log.append_row(("e1", "r1", "t", "{}", "", "", 1))
    log.append_row(("e1", "r1", "t", "{}", "", "", 1))
    assert log.count_rows() == 1


def test_inmemory_iter_filters_by_run_id() -> None:
    log = InMemoryEventLog()
    log.append_row(("e1", "r1", "t", "{}", "", "", 1))
    log.append_row(("e2", "r2", "t", "{}", "", "", 2))
    assert [r[0] for r in log.iter_rows(run_id="r1")] == ["e1"]


def test_inmemory_rows_since() -> None:
    log = InMemoryEventLog()
    for i, eid in enumerate(["e1", "e2", "e3"], start=1):
        log.append_row((eid, "r1", "t", "{}", "", "", i))
    since = log.rows_since("e2")
    assert [r[0] for r in since] == ["e3"]


def test_inmemory_rows_until() -> None:
    log = InMemoryEventLog()
    for i, eid in enumerate(["e1", "e2", "e3"], start=1):
        log.append_row((eid, "r1", "t", "{}", "", "", i))
    until = log.rows_until("e2")
    assert [r[0] for r in until] == ["e1", "e2"]


def test_inmemory_rows_since_unknown_id_returns_empty() -> None:
    log = InMemoryEventLog()
    log.append_row(("e1", "r1", "t", "{}", "", "", 1))
    assert log.rows_since("nope") == ()


# ── SQLiteEventLog ───────────────────────────────────────────────────


def test_sqlite_append_and_iter() -> None:
    log = SQLiteEventLog(":memory:")
    log.append_row(("e1", "r1", "object.created", "{}", "a", "", 1))
    log.append_row(("e2", "r1", "behavior.started", "{}", "a", "", 2))
    rows = list(log.iter_rows())
    assert [r[0] for r in rows] == ["e1", "e2"]
    log.close()


def test_sqlite_append_idempotent_on_id() -> None:
    log = SQLiteEventLog(":memory:")
    log.append_row(("e1", "r1", "t", "{}", "", "", 1))
    log.append_row(("e1", "r1", "t", "{}", "", "", 1))
    assert log.count_rows() == 1
    log.close()


def test_sqlite_rows_since_and_until() -> None:
    log = SQLiteEventLog(":memory:")
    for i, eid in enumerate(["e1", "e2", "e3"], start=1):
        log.append_row((eid, "r1", "t", "{}", "", "", i))
    assert [r[0] for r in log.rows_since("e2")] == ["e3"]
    assert [r[0] for r in log.rows_until("e2")] == ["e1", "e2"]
    log.close()


def test_sqlite_accepts_url_form() -> None:
    log = SQLiteEventLog("sqlite:///:memory:")
    log.append_row(("e1", "r1", "t", "{}", "", "", 1))
    assert log.count_rows() == 1
    log.close()


def test_sqlite_persists_to_disk(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "events.db"
    log1 = SQLiteEventLog(str(db))
    log1.append_row(("e1", "r1", "t", "{}", "", "", 1))
    log1.close()
    log2 = SQLiteEventLog(str(db))
    assert log2.count_rows() == 1
    log2.close()


# ── EventStore delegation ────────────────────────────────────────────


def test_event_store_impl_satisfies_protocol() -> None:
    assert isinstance(EventStoreImpl(InMemoryEventLog()), EventStore)


def test_event_store_impl_rejects_none_backend() -> None:
    with pytest.raises(TypeError, match="backend must be a non-None"):
        EventStoreImpl(backend=None)  # type: ignore[arg-type]


def test_event_store_append_and_iter() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    store.append(_ev("e1", ts=1))
    store.append(_ev("e2", ts=2))
    events = list(store.iter_events())
    assert [e.id for e in events] == ["e1", "e2"]
    assert all(e.payload == {"k": "v"} for e in events)


def test_event_store_events_since_and_until() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    for i, eid in enumerate(["e1", "e2", "e3"], start=1):
        store.append(_ev(eid, ts=i))
    assert [e.id for e in store.events_since("e2")] == ["e3"]
    assert [e.id for e in store.events_until("e2")] == ["e1", "e2"]


def test_event_store_swap_backend_is_one_change() -> None:
    """The key property: same EventStore API, different backend."""
    for backend in (InMemoryEventLog(), SQLiteEventLog(":memory:")):
        store = EventStoreImpl(backend)
        store.append(_ev("e1", ts=1))
        assert [e.id for e in store.iter_events()] == ["e1"]
        if hasattr(backend, "close"):
            backend.close()  # type: ignore[attr-defined]


def test_event_store_round_trips_payload() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    e = GraphEvent.now(
        "object.created",
        payload={"nested": {"a": 1}, "list": [1, 2, 3]},
        actor="x",
        run_id="r1",
    )
    store.append(e)
    got = next(iter(store.iter_events()))
    assert got.payload == {"nested": {"a": 1}, "list": [1, 2, 3]}
    assert got.actor == "x"
    assert got.run_id == "r1"
