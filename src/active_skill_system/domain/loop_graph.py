"""L1 Domain — LoopGraph provenance projection (RGLA, D009 §4.2).

The LoopGraph is a **projection** of a Loop's lifecycle events: typed vertices
(Loop, Skill, Intent, Verifier, Failure) connected by typed, append-only
provenance edges (USES, VERIFIED_BY, CREATED, LEARNS_FROM, FIXES, SUPERSEDES).
It is rebuildable from the event log (D009 §4.2), and is the source from which
a GraphStore adapter persists the graph (D010).

Two edge profiles (D009 §4.2):
  - **runtime edges** (USES) — written during execution, may change.
  - **provenance edges** (VERIFIED_BY, CREATED, FIXES, LEARNS_FROM, SUPERSEDES) —
    append-only, written once on completion; this separation prevents the
    high-coupling failure mode where editing one Loop invalidates many.

Per RLM research (D011 §5.3): the typed payload of a provenance edge IS the
sub-Loop return contract — typed outputs at sub-Loop boundaries are an
evidence-routing layer more durable than any RLM engine.

Pure domain. NO I/O, NO infrastructure imports (R002/R003). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class LoopVertexKind(StrEnum):
    """Vertex kinds in the LoopGraph (D009 §4.2)."""

    INTENT = "intent"
    LOOP = "loop"
    SKILL = "skill"
    VERIFIER = "verifier"
    FAILURE = "failure"
    CONTEXT = "context"


class LoopEdgeKind(StrEnum):
    """Typed provenance/runtime edges (D009 §4.2)."""

    CREATED = "created"
    USES = "uses"
    VERIFIED_BY = "verified_by"
    LEARNS_FROM = "learns_from"
    FIXES = "fixes"
    SUPERSEDES = "supersedes"
    DEPENDS_ON = "depends_on"


RUNTIME_EDGE_KINDS = frozenset({LoopEdgeKind.USES, LoopEdgeKind.DEPENDS_ON})
PROVENANCE_EDGE_KINDS = frozenset(
    {LoopEdgeKind.CREATED, LoopEdgeKind.VERIFIED_BY, LoopEdgeKind.LEARNS_FROM,
     LoopEdgeKind.FIXES, LoopEdgeKind.SUPERSEDES}
)


@dataclass(frozen=True)
class LoopVertex:
    """One node in the LoopGraph.

    Carries:
      - id: unique vertex id (e.g. "loop:loop-1", "skill:sql-plan-opt").
      - kind: the LoopVertexKind.
      - label: human-readable label.
    """

    id: str
    kind: LoopVertexKind
    label: str = ""

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.id, str) or not self.id.strip():
            errors.append(f"id must be a non-empty string (got {self.id!r})")
        if not isinstance(self.kind, LoopVertexKind):
            errors.append(f"kind must be a LoopVertexKind (got {type(self.kind).__name__})")
        if not isinstance(self.label, str):
            errors.append(f"label must be a string (got {type(self.label).__name__})")
        if errors:
            raise ValueError("LoopVertex invariant violation: " + "; ".join(errors))


@dataclass(frozen=True)
class LoopEdge:
    """One typed edge in the LoopGraph.

    Carries:
      - kind: the LoopEdgeKind (typed provenance/runtime classification).
      - src / dst: vertex ids this edge connects.
      - payload: optional typed metadata (confidence, schema, timestamp). This is
        the durable evidence-routing layer (RLM §5.3); free-text payloads are
        discouraged — prefer a typed dict.
    """

    kind: LoopEdgeKind
    src: str
    dst: str
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.kind, LoopEdgeKind):
            errors.append(f"kind must be a LoopEdgeKind (got {type(self.kind).__name__})")
        if not isinstance(self.src, str) or not self.src.strip():
            errors.append(f"src must be a non-empty string (got {self.src!r})")
        if not isinstance(self.dst, str) or not self.dst.strip():
            errors.append(f"dst must be a non-empty string (got {self.dst!r})")
        if not isinstance(self.payload, dict):
            errors.append(f"payload must be a dict (got {type(self.payload).__name__})")
        if errors:
            raise ValueError("LoopEdge invariant violation: " + "; ".join(errors))


@dataclass(frozen=True)
class LoopGraph:
    """An immutable projection of a Loop's provenance graph.

    Rebuildable from events via ``project``. Edges are de-duplicated on
    (kind, src, dst). Pure data — no query engine here (that lives behind the
    GraphStore port, D010).
    """

    vertices: tuple[LoopVertex, ...] = ()
    edges: tuple[LoopEdge, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.vertices, tuple):
            raise ValueError(f"vertices must be a tuple (got {type(self.vertices).__name__})")
        if not isinstance(self.edges, tuple):
            raise ValueError(f"edges must be a tuple (got {type(self.edges).__name__})")
        # Edge endpoints must reference known vertices.
        known = {v.id for v in self.vertices}
        for e in self.edges:
            if e.src not in known:
                raise ValueError(f"edge {e!r} src {e.src!r} not in vertices")
            if e.dst not in known:
                raise ValueError(f"edge {e!r} dst {e.dst!r} not in vertices")

    def vertex(self, vertex_id: str) -> LoopVertex | None:
        for v in self.vertices:
            if v.id == vertex_id:
                return v
        return None

    def edges_from(self, vertex_id: str) -> tuple[LoopEdge, ...]:
        return tuple(e for e in self.edges if e.src == vertex_id)

    def edges_to(self, vertex_id: str) -> tuple[LoopEdge, ...]:
        return tuple(e for e in self.edges if e.dst == vertex_id)

    def has_edge(self, kind: LoopEdgeKind, src: str, dst: str) -> bool:
        return any(
            e.kind == kind and e.src == src and e.dst == dst for e in self.edges
        )


def _vid(kind: LoopVertexKind, key: str) -> str:
    """Stable vertex-id convention: '<kind>:<key>'."""
    return f"{kind.value}:{key}"


def project(loop: Any) -> LoopGraph:
    """Project a Loop's lifecycle into a LoopGraph (D009 §4.2).

    Derivation rules:
      - CREATED: intent vertex -> loop vertex (emitted on STARTED).
      - USES:    loop vertex -> skill vertices (one per declared skill).
      - VERIFIED_BY: loop -> verifier vertex (emitted on VERIFIED events whose
        payload names a verifier).
      - FIXES / LEARNS_FROM / SUPERSEDES: derived from event payloads when
        present (e.g. a FAILED event with a 'fixes' payload links the loop to
        a failure vertex).

    Idempotent and rebuildable: projecting the same loop twice yields the same
    graph. This is the source the GraphStore adapter persists (D010).
    """
    from active_skill_system.domain.loop import Loop, LoopEventKind, LoopState

    if not isinstance(loop, Loop):
        raise TypeError(f"project() expects a Loop (got {type(loop).__name__})")

    vertices: list[LoopVertex] = []
    edges: list[LoopEdge] = []
    seen_v: set[str] = set()
    seen_e: set[tuple[str, str, str]] = set()

    def _add_vertex(v: LoopVertex) -> None:
        if v.id not in seen_v:
            seen_v.add(v.id)
            vertices.append(v)

    def _add_edge(e: LoopEdge) -> None:
        key = (e.kind.value, e.src, e.dst)
        if key not in seen_e:
            seen_e.add(key)
            edges.append(e)

    loop_vid = _vid(LoopVertexKind.LOOP, loop.id)
    _add_vertex(LoopVertex(loop_vid, LoopVertexKind.LOOP, loop.id))

    intent_vid = _vid(LoopVertexKind.INTENT, loop.id)
    _add_vertex(LoopVertex(intent_vid, LoopVertexKind.INTENT, loop.intent))
    _add_edge(LoopEdge(LoopEdgeKind.CREATED, intent_vid, loop_vid))

    for skill_id in loop.skills:
        s_vid = _vid(LoopVertexKind.SKILL, skill_id)
        _add_vertex(LoopVertex(s_vid, LoopVertexKind.SKILL, skill_id))
        _add_edge(LoopEdge(LoopEdgeKind.USES, loop_vid, s_vid))

    for ev in loop.lifecycle:
        if ev.kind is LoopEventKind.VERIFIED and ev.state is LoopState.VERIFYING:
            verifier = str(ev.payload.get("verifier", "default-verifier"))
            vr_vid = _vid(LoopVertexKind.VERIFIER, verifier)
            _add_vertex(LoopVertex(vr_vid, LoopVertexKind.VERIFIER, verifier))
            _add_edge(LoopEdge(
                LoopEdgeKind.VERIFIED_BY, loop_vid, vr_vid,
                payload={"confidence": ev.payload.get("confidence")},
            ))
        elif ev.kind is LoopEventKind.FAILED and "failure" in ev.payload:
            failure = str(ev.payload["failure"])
            f_vid = _vid(LoopVertexKind.FAILURE, failure)
            _add_vertex(LoopVertex(f_vid, LoopVertexKind.FAILURE, failure))
            if "fixes" in ev.payload:
                _add_edge(LoopEdge(LoopEdgeKind.FIXES, loop_vid, f_vid))
            else:
                _add_edge(LoopEdge(LoopEdgeKind.LEARNS_FROM, loop_vid, f_vid))

    return LoopGraph(vertices=tuple(vertices), edges=tuple(edges))
