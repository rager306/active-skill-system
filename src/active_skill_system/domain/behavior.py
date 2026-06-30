"""L1 Domain — Behavior + EventMatcher (M053 S00, Wave C primitive #3).

Reactive behavior primitives: a Behavior is a named handler subscribed to
specific event types. When a matching event is published, the behavior fires.
This mirrors activegraph's BehaviorInfo (name, kind, subscribed_to, pattern,
activate_after) but is pure stdlib — no activegraph import.

These are the reactive primitives that turn the EventStore from an archive
into a live event bus. Behaviors fire automatically when events match.

Pure domain. NO I/O, NO infrastructure imports (R002/R003). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class BehaviorKind:
    """What kind of reactive behavior this is (mirrors activegraph)."""

    EVENT = "event"          # fires when an event of subscribed type is published
    PATTERN = "pattern"      # fires when a graph pattern transitions not-match → match
    RELATION = "relation"    # fires when a relation of a specific kind is created
    SCHEDULED = "scheduled"  # fires on a schedule (future, Wave D)


@dataclass(frozen=True)
class EventMatcher:
    """Predicate for filtering which events a behavior subscribes to.

    A behavior subscribes to one or more event types (e.g. "claim.created").
    Optionally, it can filter by payload attributes (e.g. {"severity": "high"}).
    """

    event_types: tuple[str, ...]
    payload_filter: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.event_types, tuple) or not self.event_types:
            errors.append(f"event_types must be non-empty tuple (got {self.event_types!r})")
        for et in self.event_types:
            if not isinstance(et, str) or not et.strip():
                errors.append(f"event_type must be non-empty string (got {et!r})")
        if not isinstance(self.payload_filter, dict):
            errors.append(f"payload_filter must be dict (got {type(self.payload_filter).__name__})")
        if errors:
            raise ValueError("EventMatcher invariant violation: " + "; ".join(errors))

    def matches(self, event_type: str, payload: dict[str, Any] | None = None) -> bool:
        """Check if an event matches this matcher.

        Args:
            event_type: the event type string (e.g. "claim.created").
            payload: the event payload dict (optional).

        Returns:
            True if event_type is in event_types AND all payload_filter
            key-value pairs are present and equal in payload.
        """
        if event_type not in self.event_types:
            return False
        if not self.payload_filter:
            return True
        if payload is None:
            return False
        return all(payload.get(key) == expected for key, expected in self.payload_filter.items())


@dataclass(frozen=True)
class Behavior:
    """A reactive behavior: a named handler subscribed to events.

    Fields:
      - name: unique behavior identifier (e.g. "evidence_check").
      - matcher: which events trigger this behavior.
      - kind: BehaviorKind (event/pattern/relation/scheduled).
      - activate_after: minimum event count before behavior activates (0 = immediate).
      - description: human-readable purpose.

    The handler itself is NOT stored here (handlers are callables registered
    at runtime via BehaviorRuntime.register). This domain type describes the
    BEHAVIOR SPEC, not the implementation.
    """

    name: str
    matcher: EventMatcher
    kind: str = BehaviorKind.EVENT
    activate_after: int = 0
    description: str = ""

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.name, str) or not self.name.strip():
            errors.append(f"name must be non-empty string (got {self.name!r})")
        if not isinstance(self.matcher, EventMatcher):
            errors.append(f"matcher must be EventMatcher (got {type(self.matcher).__name__})")
        if self.kind not in (BehaviorKind.EVENT, BehaviorKind.PATTERN,
                             BehaviorKind.RELATION, BehaviorKind.SCHEDULED):
            errors.append(f"kind must be event/pattern/relation/scheduled (got {self.kind!r})")
        if not isinstance(self.activate_after, int) or self.activate_after < 0:
            errors.append(f"activate_after must be non-negative int (got {self.activate_after!r})")
        if not isinstance(self.description, str):
            errors.append(f"description must be string (got {type(self.description).__name__})")
        if errors:
            raise ValueError("Behavior invariant violation: " + "; ".join(errors))

    def should_activate(self, events_processed: int) -> bool:
        """Check if this behavior should activate given the event count.

        Args:
            events_processed: number of events processed so far in the run.

        Returns:
            True if events_processed >= activate_after.
        """
        return events_processed >= self.activate_after

    def matches(self, event_type: str, payload: dict[str, Any] | None = None) -> bool:
        """Delegate to matcher."""
        return self.matcher.matches(event_type, payload)
