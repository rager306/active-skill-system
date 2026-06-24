"""L3 Adapter — TaskGraph ↔ activegraph bridge (M004, R1 prototype).

This adapter is the load-bearing seam that turns R1 (Task Graph ↔ activegraph
mapping) from a CONTEXT agreement into code. It does NOT import activegraph
directly: it serializes domain operations to structured ``EventSink.emit(...)``
calls, and (S02) deserializes activegraph events back into domain operations.
That keeps the bridge testable with a fake sink, and leaves the activegraph-
side ``graph.emit(...)`` wiring to a thin ``ActivegraphEventSink`` (M005+).

The bridge is intentionally narrow — it is the prototype R1 calls for, not a
production mapping. Production concerns (object types, replay divergence, fork
isolation) live in the activegraph side and in M005+.

Layering:
  - Adapters (L3) may import activegraph — but this module does NOT, so the
    pure-domain tests + 5 outbound-операций stay green without activegraph.
  - Domain (L1) and Application (L2) do not import this module (R002).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from active_skill_system.domain.runtime import (
    ClaimStatus,
    RunFSM,
    RunState,
    TaskEdge,
    TaskGraph,
    TaskNode,
)

# ── event type constants (the M003/M004 vocabulary) ─────────────────────────


EVENT_NODE_ADDED = "task.node.added"
EVENT_EDGE_ADDED = "task.edge.added"
EVENT_GRAPH_COMMITTED = "task.graph.committed"
EVENT_CLAIM_PROMOTED = "task.claim.promoted"
EVENT_FSM_TRANSITIONED = "task.fsm.transitioned"


# ── inbound (S02) — TaskGraphState + apply_event ────────────────────────


@dataclass(frozen=True)
class TaskGraphState:
    """Reconstructed domain state, materialised from a stream of bridge events.

    Carries:
      - graph: the latest TaskGraph (current_version + parent linkage).
      - claim_statuses: id -> ClaimStatus, the latest observed status per claim.
      - run_fsm: the latest observed RunFSM (None until an fsm event is replayed).

    The state is immutable: ``apply_event`` returns a NEW state. This makes the
    S02 round-trip (outbound → collect → apply_event) a pure transformation,
    testable with no activegraph runtime.
    """

    graph: TaskGraph = field(default_factory=TaskGraph)
    claim_statuses: dict[str, ClaimStatus] = field(default_factory=dict)
    run_fsm: RunFSM | None = None

    def apply_event(self, event_type: str, payload: dict[str, Any]) -> TaskGraphState:
        """Return a new state with ``event_type``/``payload`` applied.

        Unknown event types are no-ops (forward-compat: replaying a stream
        with newer event types must not crash older state).
        """
        if event_type == EVENT_NODE_ADDED:
            node = _deserialize_node(payload)
            return TaskGraphState(
                graph=self.graph.add_node(node),
                claim_statuses=self.claim_statuses,
                run_fsm=self.run_fsm,
            )
        if event_type == EVENT_EDGE_ADDED:
            edge = _deserialize_edge(payload)
            return TaskGraphState(
                graph=self.graph.add_edge(edge),
                claim_statuses=self.claim_statuses,
                run_fsm=self.run_fsm,
            )
        if event_type == EVENT_GRAPH_COMMITTED:
            return TaskGraphState(
                graph=self.graph.commit(),
                claim_statuses=self.claim_statuses,
                run_fsm=self.run_fsm,
            )
        if event_type == EVENT_CLAIM_PROMOTED:
            return TaskGraphState(
                graph=self.graph,
                claim_statuses={
                    **self.claim_statuses,
                    payload["claim_id"]: ClaimStatus(payload["new_status"]),
                },
                run_fsm=self.run_fsm,
            )
        if event_type == EVENT_FSM_TRANSITIONED:
            fsm = self.run_fsm or RunFSM()
            return TaskGraphState(
                graph=self.graph,
                claim_statuses=self.claim_statuses,
                run_fsm=fsm.transition(RunState(payload["new_state"])),
            )
        # Unknown event: forward-compat no-op.
        return self


# ── port + value object ───────────────────────────────────────────────────


class EventSink(Protocol):
    """Injectable sink for emitted events (the only port the bridge depends on).

    Production replaces this with ``ActivegraphEventSink`` (M005+). Tests inject
    ``ListEventSink``. The bridge is unaware of the underlying transport.
    """

    def emit(self, event_type: str, payload: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class ActivegraphEmitted:
    """One emitted event (for tests + replay inspection)."""

    event_type: str
    payload: dict[str, Any]


@dataclass
class ListEventSink:
    """In-memory EventSink that records every emitted event (testing / dev)."""

    events: list[ActivegraphEmitted] = field(default_factory=list)

    def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append(ActivegraphEmitted(event_type=event_type, payload=dict(payload)))


# ── bridge ────────────────────────────────────────────────────────────────


def _node_payload(node: TaskNode) -> dict[str, Any]:
    """Serialize a TaskNode to a round-trip-ready dict.

    The id is its .value (a plain string) so the inbound side can reconstruct
    the TaskNodeId without needing the original object.
    """
    return {
        "id": str(node.id),
        "kind": node.kind.value,
        "text": node.text,
    }


def _edge_payload(edge: TaskEdge) -> dict[str, Any]:
    return {
        "source": str(edge.source),
        "target": str(edge.target),
        "kind": edge.kind.value,
    }


def _claim_payload(claim_id: str, prev: ClaimStatus, new: ClaimStatus) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "prev_status": prev.value,
        "new_status": new.value,
    }


def _fsm_payload(run_id: str, prev: str, new: str) -> dict[str, Any]:
    return {"run_id": run_id, "prev_state": prev, "new_state": new}


class TaskGraphBridge:
    """Outbound projection of domain operations → activegraph emits.

    The application layer calls these methods after each domain operation so
    the events end up in activegraph (production) or in memory (tests). The
    S02 inbound methods (``apply_event``) consume the same payloads to
    reconstruct the domain.
    """

    def __init__(self, sink: EventSink) -> None:
        self._sink = sink

    # ── graph (S01) ────────────────────────────────────────────────────────

    def on_node_added(self, node: TaskNode) -> None:
        self._sink.emit(EVENT_NODE_ADDED, _node_payload(node))

    def on_edge_added(self, edge: TaskEdge) -> None:
        self._sink.emit(EVENT_EDGE_ADDED, _edge_payload(edge))

    def on_graph_committed(self, graph: TaskGraph, prev_version: int) -> None:
        self._sink.emit(
            EVENT_GRAPH_COMMITTED,
            {"version": graph.version, "prev_version": prev_version},
        )

    # ── claim (S01) ────────────────────────────────────────────────────────

    def on_claim_promoted(
        self, claim_id: str, prev_status: ClaimStatus, new_status: ClaimStatus
    ) -> None:
        self._sink.emit(
            EVENT_CLAIM_PROMOTED, _claim_payload(claim_id, prev_status, new_status)
        )

    # ── fsm (S01) ──────────────────────────────────────────────────────────

    def on_fsm_transitioned(
        self, run_id: str, prev_state_value: str, new_state_value: str
    ) -> None:
        self._sink.emit(
            EVENT_FSM_TRANSITIONED,
            _fsm_payload(run_id, prev_state_value, new_state_value),
        )

    # ── helpers (S01, used by S02 round-trip tests) ───────────────────────

    @property
    def events(self) -> Iterable[ActivegraphEmitted]:
        """Re-export ListEventSink.events when the sink is a ListEventSink.

        Type-narrowed helper for tests; production sinks expose no events.
        """
        events = getattr(self._sink, "events", None)
        if events is None:
            raise AttributeError(
                "sink has no .events (production sinks don't buffer); use a ListEventSink in tests"
            )
        return events


# ── inbound (S02) ───────────────────────────────────────────────────────────
# Kept here so the bridge module is a single import surface. S02 expands this
# to the full round-trip with apply_event + EventLog.


def _deserialize_node(payload: dict[str, Any]) -> TaskNode:
    """Rebuild a TaskNode from its outbound payload (S02)."""
    from active_skill_system.domain.runtime import NodeKind, TaskNodeId

    return TaskNode(
        id=TaskNodeId(payload["id"]),
        kind=NodeKind(payload["kind"]),
        text=payload.get("text", ""),
    )


def _deserialize_edge(payload: dict[str, Any]) -> TaskEdge:
    """Rebuild a TaskEdge from its outbound payload (S02)."""
    from active_skill_system.domain.runtime import EdgeKind, TaskNodeId

    return TaskEdge(
        source=TaskNodeId(payload["source"]),
        target=TaskNodeId(payload["target"]),
        kind=EdgeKind(payload["kind"]),
    )
