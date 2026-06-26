"""L2 (port adapter, pure-Python stub) — RuVector container (M035 S01).

This is a pure-Python stub for the future Rust + PyO3 implementation.
The API surface (`RuVectorContainer`) is stable; the real implementation
will replace this module with PyO3-backed code in a future milestone
without changing the public API.

Pure Python. NO infrastructure imports (R002 compatible at the Python
level; the real PyO3 build will move infra into L3 but the public
interface stays the same).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

__version__ = "0.1.0"


@dataclass(frozen=True)
class Event:
    """An event in the container.

    Carries:
      - id: unique event id.
      - event_type: semantic type (e.g. "thought", "claim").
      - payload: free-form dict.
      - timestamp: ISO 8601 string.
    """

    id: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


class RuVectorContainer:
    """Pure-Python stub of the container format for AI agent knowledge graphs.

    The real Rust + PyO3 implementation will replace the internals while
    keeping this API stable. Events are stored in-memory (this stub does
    not persist); the PyO3 build will add a backing store.
    """

    def __init__(self, path: str = ":memory:") -> None:
        if not isinstance(path, str):
            raise TypeError(f"path must be a string (got {type(path).__name__})")
        self._path = path
        self._events: list[Event] = []

    @property
    def path(self) -> str:
        return self._path

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self):
        return iter(self._events)

    def add_event(self, event_id: str, event_type: str, payload: dict[str, Any] | None = None) -> Event:
        """Add an event to the container.

        Returns the Event that was added.
        """
        if not isinstance(event_id, str) or not event_id:
            raise ValueError(f"event_id must be a non-empty string (got {event_id!r})")
        if not isinstance(event_type, str) or not event_type:
            raise ValueError(f"event_type must be a non-empty string (got {event_type!r})")
        ev = Event(
            id=event_id,
            event_type=event_type,
            payload=dict(payload) if payload is not None else {},
            timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        self._events.append(ev)
        return ev

    def query(self, event_type: str | None = None) -> list[Event]:
        """Return all events (optionally filtered by type)."""
        if event_type is None:
            return list(self._events)
        return [e for e in self._events if e.event_type == event_type]

    def get(self, event_id: str) -> Event | None:
        for e in self._events:
            if e.id == event_id:
                return e
        return None


__all__ = ["Event", "RuVectorContainer", "__version__"]
