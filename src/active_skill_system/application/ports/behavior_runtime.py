"""L2 Application — BehaviorRuntime port (M053 S01, Wave C primitive #3).

The reactive runtime port: register behaviors with handlers, publish events,
dispatch to matching behaviors. This turns the EventStore from an archive
into a live event bus.

Adapters:
  - InMemoryBehaviorRuntime (S02) — sync dispatch, in-memory handler registry.
  - NativeBehaviorRuntime (future) — persists behavior state, async dispatch.

This port is the swap seam: if we later want activegraph's reactive runtime
(with its behavior/pack model), we swap the adapter without touching the
application layer.

The BehaviorContext gives handlers access to the current event, a graph
snapshot, and an emit callback (to propose patches or publish follow-up
events).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from active_skill_system.domain.behavior import Behavior
from active_skill_system.domain.graph_primitives import GraphEvent


@dataclass(frozen=True)
class BehaviorContext:
    """Context passed to a behavior handler when it fires.

    Fields:
      - event: the GraphEvent that triggered this behavior.
      - graph_snapshot: read-only view of the current graph state (dict of
        vertex_id -> vertex_data, or None if no graph backend is wired).
      - emit: callback to publish follow-up events or propose patches.
        Handlers call emit(GraphEvent(...)) to chain reactions.
      - run_id: the current run ID.
      - events_processed: number of events processed so far (for activate_after).

    Handlers are pure functions: (context) -> None. Side effects happen
    through emit() (which feeds back into the runtime) or through patches
    (proposed via PatchApplier in S03).
    """

    event: GraphEvent
    graph_snapshot: dict[str, Any] | None = None
    emit: Callable[[GraphEvent], None] | None = None
    run_id: str = ""
    events_processed: int = 0


# Type alias for behavior handler functions.
BehaviorHandler = Callable[[BehaviorContext], None]


@dataclass
class BehaviorRegistration:
    """A registered behavior + its handler function."""

    behavior: Behavior
    handler: BehaviorHandler
    fire_count: int = 0
    error_count: int = 0
    last_error: str = ""


@runtime_checkable
class BehaviorRuntime(Protocol):
    """Reactive behavior runtime: events trigger behaviors automatically.

    register(behavior, handler) adds a behavior to the runtime.
    publish(event) dispatches the event to all matching registered behaviors.
    dispatch(event_type, payload) is a convenience for publishing a new event.

    Handlers receive a BehaviorContext. They can emit follow-up events via
    context.emit() to chain reactions. Handler exceptions are caught and
    logged as behavior.failed events (the runtime never crashes from a
    handler error).
    """

    def register(self, behavior: Behavior, handler: BehaviorHandler) -> None:
        """Register a behavior with its handler function."""
        ...

    def publish(self, event: GraphEvent) -> None:
        """Publish an event to all matching registered behaviors.

        Dispatches synchronously to all behaviors whose matcher matches
        the event type + payload and whose activate_after is satisfied.
        Handler exceptions are caught and logged.
        """
        ...

    def list_registrations(self) -> list[BehaviorRegistration]:
        """List all registered behaviors (for debugging/introspection)."""
        ...
