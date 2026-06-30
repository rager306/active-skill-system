"""L3 Adapter — PatternBehaviorRuntime (M053 S07, Wave C primitive #9).

Extends InMemoryBehaviorRuntime with pattern-based triggers. When a graph
mutation causes a Pattern to transition from not-matching to matching,
the registered behavior fires automatically.

This combines Wave C primitives #3 (Behaviors) and #9 (Patterns) into a
graph-reactive runtime: the system reacts not just to events but to
graph-structure transitions.

The PatternBehaviorRuntime wraps an InMemoryBehaviorRuntime and adds a
pattern registry. After each graph mutation (via check_patterns()), it
evaluates registered patterns and fires behaviors for newly-matching ones.
"""

from __future__ import annotations

import logging
from typing import Any

from active_skill_system.adapters.inmemory_behavior_runtime import InMemoryBehaviorRuntime
from active_skill_system.application.ports.behavior_runtime import BehaviorHandler
from active_skill_system.domain.behavior import BehaviorKind
from active_skill_system.domain.graph_primitives import GraphEvent
from active_skill_system.domain.pattern import GraphView, Pattern, PatternMatcher

logger = logging.getLogger(__name__)


class PatternTriggerRegistration:
    """A registered pattern trigger + its handler."""

    def __init__(self, pattern: Pattern, handler: BehaviorHandler,
                 behavior_name: str = "") -> None:
        self.pattern = pattern
        self.handler = handler
        self.behavior_name = behavior_name or f"pattern.{pattern.name}"
        self.last_matched: bool = False
        self.fire_count: int = 0


class PatternBehaviorRuntime(InMemoryBehaviorRuntime):
    """BehaviorRuntime + pattern triggers (graph-reactive).

    Extends InMemoryBehaviorRuntime:
      - register_pattern(pattern, handler): register a graph-shape trigger.
      - check_patterns(graph_view): evaluate all registered patterns. If a
        pattern transitions from not-matching to matching, fire its handler.
      - Pattern-triggered handlers receive a synthetic GraphEvent
        (type="pattern.matched") as context.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pattern_triggers: list[PatternTriggerRegistration] = []
        self._matcher = PatternMatcher()

    def register_pattern(
        self,
        pattern: Pattern,
        handler: BehaviorHandler,
        behavior_name: str = "",
    ) -> None:
        """Register a pattern trigger. Handler fires when pattern newly matches."""
        if not isinstance(pattern, Pattern):
            raise TypeError(f"pattern must be a Pattern (got {type(pattern).__name__})")
        if not callable(handler):
            raise TypeError(f"handler must be callable (got {type(handler).__name__})")
        self._pattern_triggers.append(
            PatternTriggerRegistration(pattern, handler, behavior_name)
        )

    def check_patterns(self, graph_view: GraphView, run_id: str = "") -> int:
        """Evaluate all registered patterns against the current graph.

        For each pattern that transitions from not-matching to matching,
        fire its handler with a synthetic pattern.matched event.

        Returns the number of patterns that newly matched (fired).
        """
        fired_count = 0
        for reg in self._pattern_triggers:
            now_matches = self._matcher.matches(reg.pattern, graph_view)

            # Only fire on transition: not-matching → matching.
            if now_matches and not reg.last_matched:
                fired_count += 1
                reg.fire_count += 1
                reg.last_matched = True

                # Create a synthetic event for the pattern match.
                event = GraphEvent(
                    id=f"pattern.{reg.pattern.name}.{reg.fire_count}",
                    type="pattern.matched",
                    payload={
                        "pattern_name": reg.pattern.name,
                        "description": reg.pattern.description,
                    },
                    actor="pattern_runtime",
                    run_id=run_id,
                    timestamp_ns=self.events_processed + 1,
                )

                # Dispatch via parent (respects trace instrumentation + error handling).
                # We dispatch directly to avoid re-entering check_patterns.
                self._dispatch_pattern_handler(reg, event)
            elif not now_matches:
                # Pattern no longer matches — reset for next transition.
                reg.last_matched = False

        return fired_count

    def _dispatch_pattern_handler(
        self, reg: PatternTriggerRegistration, event: GraphEvent,
    ) -> None:
        """Dispatch a pattern trigger handler (same error handling as event dispatch)."""
        from active_skill_system.application.ports.behavior_runtime import BehaviorContext

        span_id = None
        if self._trace is not None:
            span_id = self._trace.start_span(
                f"behavior.{reg.behavior_name}",
                parent=None,
                layer="application",
                event_type=event.type,
                behavior_kind=BehaviorKind.PATTERN,
                pattern_name=reg.pattern.name,
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
            if span_id is not None:
                self._trace.end_span(span_id, status="ok")
        except Exception as e:  # noqa: BLE001
            logger.error(
                "pattern trigger %s failed: %s", reg.behavior_name, e,
                exc_info=True,
            )
            if span_id is not None:
                self._trace.end_span(span_id, status="error", error=str(e))

    def list_pattern_triggers(self) -> list[PatternTriggerRegistration]:
        """List all registered pattern triggers (for debugging)."""
        return list(self._pattern_triggers)
