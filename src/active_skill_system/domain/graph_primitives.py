"""L1 Domain — Generic graph primitives (M051 S01, Wave A).

Backend-agnostic graph types. These are the GENERIC primitives the
``GraphBackend`` port (application/ports/graph_backend.py) speaks. They are
distinct from the Loop-specific ``LoopVertex``/``LoopEdge`` in
``domain/loop_graph.py``: those are a SPECIALISED projection of a Loop's
lifecycle; these are the generic vertex/edge that any graph store can hold.

The split lets us:
  - swap the backing store (LadybugDB → HelixDB → FalkorDB) without touching
    the application layer;
  - add a generic event log (``GraphEvent``) that any runtime can replay.

Pure domain. NO I/O, NO infrastructure imports (R002/R003). stdlib only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class Vertex:
    """A generic graph vertex.

    Fields:
      - id: unique vertex id (caller-chosen, e.g. "loop:abc", "claim:42").
      - type: vertex type label (e.g. "loop", "claim", "intent"). Free-form
        string — the backend does not enforce a schema.
      - data: arbitrary JSON-serialisable payload (dict).
    """

    id: str
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.id, str) or not self.id.strip():
            errors.append(f"id must be a non-empty string (got {self.id!r})")
        if not isinstance(self.type, str) or not self.type.strip():
            errors.append(f"type must be a non-empty string (got {self.type!r})")
        if not isinstance(self.data, dict):
            errors.append(f"data must be a dict (got {type(self.data).__name__})")
        if errors:
            raise ValueError("Vertex invariant violation: " + "; ".join(errors))


@dataclass(frozen=True)
class Edge:
    """A generic typed graph edge.

    Fields:
      - kind: edge type label (e.g. "uses", "verified_by", "supports").
      - src: source vertex id.
      - dst: destination vertex id.
      - data: arbitrary JSON-serialisable payload (dict).
    """

    kind: str
    src: str
    dst: str
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.kind, str) or not self.kind.strip():
            errors.append(f"kind must be a non-empty string (got {self.kind!r})")
        if not isinstance(self.src, str) or not self.src.strip():
            errors.append(f"src must be a non-empty string (got {self.src!r})")
        if not isinstance(self.dst, str) or not self.dst.strip():
            errors.append(f"dst must be a non-empty string (got {self.dst!r})")
        if not isinstance(self.data, dict):
            errors.append(f"data must be a dict (got {type(self.data).__name__})")
        if errors:
            raise ValueError("Edge invariant violation: " + "; ".join(errors))


class GraphEventType:
    """Catalog of well-known event types (mirrors activegraph's vocabulary).

    These are STRINGS, not an enum: behaviors may emit custom event types
    (any string). The well-known ones are documented here for discoverability.

    Lifecycle:  goal.created, runtime.idle, runtime.budget_exhausted
    Graph:      object.created, object.removed, relation.created, relation.removed
    Behaviors:  behavior.scheduled, behavior.started, behavior.completed,
                behavior.failed, relation_behavior.started
    Patterns:   pattern.matched
    LLM:        llm.requested, llm.responded
    Tools:      tool.requested, tool.responded
    Patches:    patch.proposed, patch.applied, patch.rejected
    Approvals:  approval.proposed, approval.granted
    Packs:      pack.loaded
    Custom:     any string (application-level events)
    """

    OBJECT_CREATED = "object.created"
    RELATION_CREATED = "relation.created"
    BEHAVIOR_STARTED = "behavior.started"
    BEHAVIOR_COMPLETED = "behavior.completed"
    BEHAVIOR_FAILED = "behavior.failed"
    LLM_REQUESTED = "llm.requested"
    LLM_RESPONDED = "llm.responded"
    # Trajectory-step aliases (our SandboxAgentRunner emits these):
    TRAJECTORY_STEP = "trajectory.step"


@dataclass(frozen=True)
class GraphEvent:
    """One record in the append-only event log.

    Mirrors activegraph's Event shape but is OUR type (stdlib-only). The
    EventStore port persists these; the EventLogBackend translates to row
    tuples for whatever DB (SQLite/Postgres/in-memory).

    Fields:
      - id: unique event id (uuid hex by default).
      - type: event type string (see GraphEventType for well-known ones).
      - payload: arbitrary JSON-serialisable data dict.
      - actor: who/what emitted the event (e.g. "sandbox-agent", "user").
      - run_id: which run this event belongs to (for replay/fork grouping).
      - caused_by: optional id of the event that caused this one (causality).
      - timestamp_ns: monotonic-ish nanosecond timestamp (ordering).
    """

    id: str
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    actor: str = ""
    run_id: str = ""
    caused_by: str = ""
    timestamp_ns: int = 0

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.id, str) or not self.id.strip():
            errors.append(f"id must be a non-empty string (got {self.id!r})")
        if not isinstance(self.type, str) or not self.type.strip():
            errors.append(f"type must be a non-empty string (got {self.type!r})")
        if not isinstance(self.payload, dict):
            errors.append(f"payload must be a dict (got {type(self.payload).__name__})")
        if errors:
            raise ValueError("GraphEvent invariant violation: " + "; ".join(errors))

    @staticmethod
    def now(
        type_: str,
        *,
        payload: dict[str, Any] | None = None,
        actor: str = "",
        run_id: str = "",
        caused_by: str = "",
        event_id: str | None = None,
    ) -> GraphEvent:
        """Build a GraphEvent with an auto-generated id + current timestamp."""
        return GraphEvent(
            id=event_id or f"evt-{uuid.uuid4().hex[:12]}",
            type=type_,
            payload=payload or {},
            actor=actor,
            run_id=run_id,
            caused_by=caused_by,
            timestamp_ns=int(datetime.now(UTC).timestamp() * 1_000_000_000),
        )
