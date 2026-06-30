"""L3 Adapter — EventEmittingBehaviorRuntime (M053 S10, Wave C audit trail).

Wraps InMemoryBehaviorRuntime to emit GraphEvents for every reactive operation:
  - behavior.triggered (when a behavior fires)
  - behavior.failed (when a behavior handler raises)
  - patch.proposed (when a behavior proposes a patch)
  - patch.applied (when an approved patch is applied)
  - policy.approved (when a policy approves a patch)
  - policy.rejected (when a policy rejects a patch)
  - pattern.matched (when a pattern trigger fires)

This makes the reactive system fully auditable: --event-stats and --diff
show behavior/policy/pattern activity. The event log becomes the single
source of truth for reactive behavior.
"""

from __future__ import annotations

import logging
from typing import Any

from active_skill_system.adapters.inmemory_behavior_runtime import InMemoryBehaviorRuntime
from active_skill_system.application.ports.behavior_runtime import BehaviorContext
from active_skill_system.application.ports.event_store import EventStore
from active_skill_system.domain.graph_primitives import GraphEvent

logger = logging.getLogger(__name__)


class EventEmittingBehaviorRuntime(InMemoryBehaviorRuntime):
    """BehaviorRuntime that emits GraphEvents for all reactive operations.

    Wraps the dispatch to emit behavior.triggered and behavior.failed events
    to the EventStore. Patch/policy events are emitted by wrapping the
    PatchApplier and PolicyGate (see EventEmittingPatchApplier).
    """

    def __init__(self, event_store: EventStore, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if event_store is None:
            raise TypeError("event_store must be a non-None EventStore")
        self._store = event_store

    def _dispatch(self, event: GraphEvent) -> None:
        """Override to emit behavior.triggered/failed events."""
        for reg in self._registrations:
            b = reg.behavior
            if not b.should_activate(self._events_processed):
                continue
            if not b.matches(event.type, event.payload):
                continue

            # Emit behavior.triggered.
            self._emit_event("behavior.triggered", event.run_id, {
                "behavior_name": b.name,
                "trigger_event_id": event.id,
                "trigger_event_type": event.type,
            })

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
                logger.error("behavior %s failed: %s", b.name, e, exc_info=True)

                # Emit behavior.failed.
                self._emit_event("behavior.failed", event.run_id, {
                    "behavior_name": b.name,
                    "error": str(e),
                    "trigger_event_id": event.id,
                })

                if span_id is not None:
                    self._trace.end_span(span_id, status="error", error=str(e))

    def _emit_event(self, event_type: str, run_id: str, payload: dict[str, Any]) -> None:
        """Emit a GraphEvent to the EventStore."""
        try:
            self._store.append(GraphEvent(
                id=f"{event_type}.{self._events_processed}.{run_id}",
                type=event_type,
                payload=payload,
                actor="behavior_runtime",
                run_id=run_id,
                timestamp_ns=self._events_processed,
            ))
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to emit event %s: %s", event_type, e)
