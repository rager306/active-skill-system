"""L3 Adapter — RelationBehaviorRuntime (M054 S03, Wave D primitive #4).

Extends PatternBehaviorRuntime with relation-based triggers. When an edge
of a specific kind/type is created, the registered RelationBehavior fires.

This combines Wave D primitive #4 (Relations) with the M053 reactive runtime.
Edge-level reactivity complements event-level (BehaviorRuntime) and
graph-level (PatternMatcher) reactivity.

Usage:
    rt = RelationBehaviorRuntime()
    rt.register_relation_behavior(
        RelationBehavior(name="linker", relation=Relation(
            kind="supports", source_type="evidence", target_type="claim")),
        handler,
    )
    rt.check_relations(graph_view)  # fires handlers for newly-created edges
"""

from __future__ import annotations

import logging
from typing import Any

from active_skill_system.adapters.pattern_behavior_runtime import (
    PatternBehaviorRuntime,
)
from active_skill_system.application.ports.behavior_runtime import (
    BehaviorContext,
    BehaviorHandler,
)
from active_skill_system.domain.behavior import BehaviorKind
from active_skill_system.domain.graph_primitives import GraphEvent
from active_skill_system.domain.relation import RelationBehavior

logger = logging.getLogger(__name__)


class RelationTriggerRegistration:
    """A registered relation trigger + its handler."""

    def __init__(self, relation_behavior: RelationBehavior, handler: BehaviorHandler) -> None:
        self.relation_behavior = relation_behavior
        self.handler = handler
        self.fired_edges: set[str] = set()  # track which edges already fired
        self.fire_count: int = 0


class RelationBehaviorRuntime(PatternBehaviorRuntime):
    """BehaviorRuntime + pattern triggers + relation triggers.

    Extends PatternBehaviorRuntime (M053 S07) with relation-based triggers.
    register_relation_behavior(rel_behavior, handler) adds an edge trigger.
    check_relations(graph_view) evaluates edges; for each edge matching a
    registered relation that hasn't fired yet, the handler fires.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._relation_triggers: list[RelationTriggerRegistration] = []

    def register_relation_behavior(
        self,
        relation_behavior: RelationBehavior,
        handler: BehaviorHandler,
    ) -> None:
        """Register a relation trigger. Handler fires when a matching edge is created."""
        if not isinstance(relation_behavior, RelationBehavior):
            raise TypeError(
                f"relation_behavior must be a RelationBehavior "
                f"(got {type(relation_behavior).__name__})"
            )
        if not callable(handler):
            raise TypeError(f"handler must be callable (got {type(handler).__name__})")
        self._relation_triggers.append(
            RelationTriggerRegistration(relation_behavior, handler)
        )

    def check_relations(
        self, graph_view: Any, run_id: str = "",
    ) -> int:
        """Evaluate edges against registered relation triggers.

        For each edge matching a registered relation that hasn't fired yet,
        fire the handler with a synthetic relation.created event.

        Returns the number of newly-fired relation triggers.
        """
        from active_skill_system.domain.pattern import GraphView

        if not isinstance(graph_view, GraphView):
            graph_view = GraphView()

        fired_count = 0
        for reg in self._relation_triggers:
            rb = reg.relation_behavior
            if not rb.activate_after <= self._events_processed:
                continue

            for edge in graph_view.edges:
                edge_key = f"{edge.get('kind', '')}|{edge.get('source', '')}|{edge.get('target', '')}"
                if edge_key in reg.fired_edges:
                    continue

                # Check if edge matches the relation type.
                source_type = graph_view.vertices.get(edge.get("source", ""), {}).get("type", "")
                target_type = graph_view.vertices.get(edge.get("target", ""), {}).get("type", "")
                edge_kind = edge.get("kind", "")

                if rb.matches_edge(edge_kind, source_type, target_type):
                    fired_count += 1
                    reg.fire_count += 1
                    reg.fired_edges.add(edge_key)

                    # Create synthetic event.
                    event = GraphEvent(
                        id=f"relation.{rb.name}.{reg.fire_count}",
                        type="relation.created",
                        payload={
                            "relation_behavior_name": rb.name,
                            "edge_kind": edge_kind,
                            "source": edge.get("source", ""),
                            "target": edge.get("target", ""),
                        },
                        actor="relation_runtime",
                        run_id=run_id,
                        timestamp_ns=self._events_processed + 1,
                    )

                    self._dispatch_relation_handler(reg, event)

        return fired_count

    def _dispatch_relation_handler(
        self, reg: RelationTriggerRegistration, event: GraphEvent,
    ) -> None:
        """Dispatch a relation trigger handler (same error handling as parent)."""
        span_id = None
        if self._trace is not None:
            span_id = self._trace.start_span(
                f"behavior.{reg.relation_behavior.name}",
                parent=None,
                layer="application",
                event_type=event.type,
                behavior_kind=BehaviorKind.RELATION,
                relation_kind=reg.relation_behavior.relation.kind,
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
            if span_id is not None and self._trace is not None:
                self._trace.end_span(span_id, status="ok")
        except Exception as e:  # noqa: BLE001
            logger.error(
                "relation trigger %s failed: %s", reg.relation_behavior.name, e,
                exc_info=True,
            )
            if span_id is not None and self._trace is not None:
                self._trace.end_span(span_id, status="error", error=str(e))

    def list_relation_triggers(self) -> list[RelationTriggerRegistration]:
        """List all registered relation triggers (for debugging)."""
        return list(self._relation_triggers)
