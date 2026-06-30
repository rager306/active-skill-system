"""L3 Adapter — NativeReplayEngine (M054 S02, Wave D primitive #10).

ReplayEngine backed by EventStore + BehaviorRuntime. Reconstructs graph
state from an event log in strict or permissive mode.

STRICT mode: replay events into an in-memory graph WITHOUT firing behaviors.
Used for fork prefix replay — the shared prefix reconstructs state but
doesn't re-trigger reactive behavior.

PERMISSIVE mode: replay events AND fire behaviors via BehaviorRuntime (if
wired). Used for debugging "what would happen if events fired fresh".

Wave D primitive #10 (Replay) reference implementation.
"""

from __future__ import annotations

import time
from typing import Any

from active_skill_system.application.ports.event_store import EventStore
from active_skill_system.application.ports.replay_engine import ReplayEngine
from active_skill_system.domain.replay import ReplayMode, ReplayResult


class NativeReplayEngine:
    """ReplayEngine backed by EventStore. Reconstructs graph from events.

    Args:
        event_store: source of events to replay.
        behavior_runtime: optional BehaviorRuntime for permissive mode.
            If None, permissive mode behaves like strict (no behaviors to fire).
    """

    def __init__(
        self,
        event_store: EventStore,
        behavior_runtime: Any = None,
        trace: Any = None,
    ) -> None:
        if event_store is None:
            raise TypeError("event_store must be a non-None EventStore")
        self._store = event_store
        self._runtime = behavior_runtime
        self._trace = trace

    def replay(self, run_id: str, mode: str = ReplayMode.STRICT) -> ReplayResult:
        """Replay the event log for a run into a reconstructed graph.

        Args:
            run_id: the run to replay.
            mode: "strict" (no behaviors) or "permissive" (behaviors fire).

        Returns:
            ReplayResult with reconstructed graph state + counts.
        """
        if mode not in (ReplayMode.STRICT, ReplayMode.PERMISSIVE):
            raise ValueError(f"mode must be strict/permissive (got {mode!r})")

        # Start trace span for replay operation.
        span_id = None
        if self._trace is not None:
            span_id = self._trace.start_span(
                f"replay.{mode}",
                parent=None,
                layer="application",
                run_id=run_id,
                mode=mode,
            )

        start_ns = time.monotonic_ns()
        events = list(self._store.iter_events(run_id=run_id))
        graph: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        behaviors_fired = 0

        for event in events:
            if mode == ReplayMode.PERMISSIVE and self._runtime is not None:
                # Publish event to behavior runtime (behaviors may fire).
                before = sum(r.fire_count for r in self._runtime.list_registrations())
                self._runtime.publish(event)
                after = sum(r.fire_count for r in self._runtime.list_registrations())
                behaviors_fired += after - before

            # Reconstruct graph state from event payload.
            self._apply_event_to_graph(event, graph, edges)

        duration_ns = time.monotonic_ns() - start_ns

        # End trace span.
        if span_id is not None and self._trace is not None:
            self._trace.end_span(
                span_id,
                status="ok",
                events_replayed=len(events),
                vertices_reconstructed=len(graph),
                behaviors_fired=behaviors_fired,
                duration_ns=duration_ns,
            )

        return ReplayResult(
            run_id=run_id,
            mode=mode,
            events_replayed=len(events),
            vertices_reconstructed=len(graph),
            edges_reconstructed=len(edges),
            behaviors_fired=behaviors_fired,
            duration_ns=duration_ns,
            graph_snapshot=graph,
        )

    def _apply_event_to_graph(
        self,
        event: Any,
        graph: dict[str, dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> None:
        """Apply an event's payload to the graph state.

        Handles common event types:
          - object.created / vertex.upserted: add vertex to graph.
          - relation.created / edge.added: add edge to edges list.
          - patch.applied: apply patch operations to graph.
        """
        event_type = event.type
        payload = event.payload or {}

        if event_type in ("object.created", "vertex.upserted", "claim.created"):
            vertex_id = payload.get("vertex_id") or payload.get("claim_id") or payload.get("id", "")
            if vertex_id:
                graph[vertex_id] = {
                    "type": payload.get("vertex_type") or payload.get("type", "object"),
                    **{k: v for k, v in payload.items()
                       if k not in ("vertex_id", "claim_id", "id", "vertex_type", "type")},
                }

        elif event_type in ("relation.created", "edge.added"):
            edges.append({
                "kind": payload.get("kind", payload.get("edge_kind", "")),
                "source": payload.get("source", ""),
                "target": payload.get("target", ""),
            })

        elif event_type == "patch.applied":
            # Patch application: apply patch operations to graph.
            patch = payload.get("patch", {})
            if isinstance(patch, dict):
                op_type = patch.get("op_type", "")
                op_payload = patch.get("payload", {})
                if op_type == "add_node":
                    node_id = op_payload.get("node_id", "")
                    if node_id:
                        graph[node_id] = {
                            "type": op_payload.get("kind", "node"),
                            "text": op_payload.get("text", ""),
                        }
                elif op_type == "add_edge":
                    edges.append({
                        "kind": op_payload.get("kind", ""),
                        "source": op_payload.get("source", ""),
                        "target": op_payload.get("target", ""),
                    })


# NativeReplayEngine structurally satisfies ReplayEngine.
assert isinstance(NativeReplayEngine.__new__(NativeReplayEngine), ReplayEngine)  # type: ignore[arg-type]
