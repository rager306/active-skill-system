"""L3 Adapter — InMemoryBehaviorRuntime (M053 S02, Wave C primitive #3).

The reactive engine: register behaviors with handlers, publish events,
dispatch to matching behaviors synchronously. Handler exceptions are
caught and logged as behavior.failed events (the runtime never crashes
from a handler error).

This turns the EventStore from an archive into a live event bus. Events
published here trigger behaviors automatically — the core of what makes
a graph runtime reactive.

Wave C primitive #3 (Behaviors) delivered. Relations (#4) come via pattern
behaviors (S05/S07). Patches (#5) via PatchApplier (S03). Policies (#8)
via PolicyGate (S04). Patterns (#9) via PatternMatcher (S05).
"""

from __future__ import annotations

import logging
from typing import Any

from active_skill_system.application.ports.behavior_runtime import (
    BehaviorContext,
    BehaviorHandler,
    BehaviorRegistration,
    BehaviorRuntime,
)
from active_skill_system.domain.behavior import Behavior
from active_skill_system.domain.graph_primitives import GraphEvent

logger = logging.getLogger(__name__)


class InMemoryBehaviorRuntime:
    """In-memory BehaviorRuntime: sync dispatch to registered behaviors.

    Behaviors are registered with handlers. When an event is published,
    all behaviors whose matcher matches the event type + payload (and whose
    activate_after is satisfied) fire their handlers synchronously.

    Handler exceptions are caught, logged, and counted — the runtime
    continues dispatching to other behaviors. This matches activegraph's
    behavior.failed model.

    Reentrancy: if a handler emits a follow-up event via context.emit(),
    that event is published immediately (depth-first dispatch). An optional
    max_depth prevents infinite loops (default 10).
    """

    def __init__(
        self,
        *,
        events_processed: int = 0,
        max_depth: int = 10,
        trace: Any = None,
    ) -> None:
        self._registrations: list[BehaviorRegistration] = []
        self._events_processed = events_processed
        self._max_depth = max_depth
        self._trace = trace
        self._current_depth = 0

    def register(self, behavior: Behavior, handler: BehaviorHandler) -> None:
        """Register a behavior with its handler."""
        if not isinstance(behavior, Behavior):
            raise TypeError(f"behavior must be a Behavior (got {type(behavior).__name__})")
        if not callable(handler):
            raise TypeError(f"handler must be callable (got {type(handler).__name__})")
        self._registrations.append(BehaviorRegistration(behavior=behavior, handler=handler))

    def publish(self, event: GraphEvent) -> None:
        """Publish an event to all matching registered behaviors.

        Dispatches synchronously to matching behaviors. Handler exceptions
        are caught and logged. Follow-up events emitted by handlers are
        dispatched recursively (up to max_depth).
        """
        self._events_processed += 1

        if self._current_depth >= self._max_depth:
            logger.warning(
                "behavior_runtime: max_depth %d reached, skipping event %s",
                self._max_depth, event.id,
            )
            return

        self._current_depth += 1
        try:
            self._dispatch(event)
        finally:
            self._current_depth -= 1

    def _dispatch(self, event: GraphEvent) -> None:
        """Dispatch event to matching behaviors."""
        for reg in self._registrations:
            b = reg.behavior
            if not b.should_activate(self._events_processed):
                continue
            if not b.matches(event.type, event.payload):
                continue

            # Start trace span if collector is wired.
            span_id = None
            if self._trace is not None:
                span_id = self._trace.start_span(
                    f"behavior.{b.name}",
                    parent=None,
                    layer="application",
                    event_type=event.type,
                    behavior_kind=b.kind,
                )

            try:
                ctx = BehaviorContext(
                    event=event,
                    graph_snapshot=None,
                    emit=self.publish,
                    run_id=event.run_id,
                    events_processed=self._events_processed,
                )
                reg.handler(ctx)
                reg.fire_count += 1
                if span_id is not None:
                    self._trace.end_span(span_id, status="ok")
            except Exception as e:  # noqa: BLE001
                reg.error_count += 1
                reg.last_error = str(e)
                logger.error(
                    "behavior %s failed on event %s: %s",
                    b.name, event.id, e,
                    exc_info=True,
                )
                if span_id is not None:
                    self._trace.end_span(span_id, status="error", error=str(e))

    def list_registrations(self) -> list[BehaviorRegistration]:
        """List all registered behaviors (for debugging/introspection)."""
        return list(self._registrations)

    @property
    def events_processed(self) -> int:
        """Total events published to this runtime."""
        return self._events_processed


# InMemoryBehaviorRuntime structurally satisfies BehaviorRuntime.
assert isinstance(
    InMemoryBehaviorRuntime(),  # type: ignore[arg-type]
    BehaviorRuntime,
)
