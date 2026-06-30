"""L1 Domain — Pattern + PatternMatcher (M053 S05, Wave C primitive #9).

A Pattern describes a graph-shape condition (e.g. "NOT EXISTS [claim without
evidence]"). When a graph mutation causes a pattern to transition from
not-matching to matching, a behavior is triggered automatically.

This mirrors activegraph's pattern subscriptions: graph-shape queries that
fire behaviors on state transitions. Combined with the BehaviorRuntime (S07),
this gives us graph-reactivity — the system reacts not just to events but
to graph-structure changes.

Pure domain. NO I/O, NO infrastructure imports (R002/R003). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class PatternCondition:
    """How a pattern evaluates against graph state."""

    EXISTS = "exists"        # pattern matches when the described shape exists
    NOT_EXISTS = "not_exists"  # pattern matches when the described shape does NOT exist


@dataclass(frozen=True)
class PatternClause:
    """A single condition clause in a pattern query.

    A pattern is a conjunction of clauses. Each clause describes a graph
    shape condition:

      - vertex_type: the vertex type to check (e.g. "claim", "evidence").
      - condition: EXISTS or NOT_EXISTS.
      - filter: attributes to match (e.g. {"status": "unverified"}).
      - edge_to: optional — requires an edge of kind `edge_kind` to/from
        another vertex type (for relationship patterns).

    Example: "claim without evidence" =
      PatternClause(vertex_type="claim", condition=EXISTS, filter={"status": "open"})
      + PatternClause(vertex_type="evidence", condition=NOT_EXISTS,
                      edge_to={"kind": "supports", "target_type": "claim"})

    When this pattern matches (a claim exists with no supporting evidence),
    a behavior fires.
    """

    vertex_type: str
    condition: str = PatternCondition.EXISTS
    filter: dict[str, Any] = field(default_factory=dict)
    edge_to: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.vertex_type, str) or not self.vertex_type.strip():
            errors.append(f"vertex_type must be non-empty string (got {self.vertex_type!r})")
        if self.condition not in (PatternCondition.EXISTS, PatternCondition.NOT_EXISTS):
            errors.append(f"condition must be exists/not_exists (got {self.condition!r})")
        if not isinstance(self.filter, dict):
            errors.append(f"filter must be dict (got {type(self.filter).__name__})")
        if not isinstance(self.edge_to, dict):
            errors.append(f"edge_to must be dict (got {type(self.edge_to).__name__})")
        if errors:
            raise ValueError("PatternClause invariant violation: " + "; ".join(errors))


@dataclass(frozen=True)
class Pattern:
    """A graph-shape pattern that triggers behaviors on transitions.

    A pattern is a conjunction of PatternClauses. The pattern "matches" when
    ALL clauses are satisfied against the current graph state.

    Fields:
      - name: unique pattern identifier.
      - clauses: tuple of PatternClause (ALL must match).
      - description: human-readable purpose.

    When a graph mutation causes this pattern to transition from not-matching
    to matching, the registered behavior fires (S07).
    """

    name: str
    clauses: tuple[PatternClause, ...]
    description: str = ""

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.name, str) or not self.name.strip():
            errors.append(f"name must be non-empty string (got {self.name!r})")
        if not isinstance(self.clauses, tuple) or not self.clauses:
            errors.append(f"clauses must be non-empty tuple (got {self.clauses!r})")
        for clause in self.clauses:
            if not isinstance(clause, PatternClause):
                errors.append(f"clause must be PatternClause (got {type(clause).__name__})")
        if not isinstance(self.description, str):
            errors.append(f"description must be string (got {type(self.description).__name__})")
        if errors:
            raise ValueError("Pattern invariant violation: " + "; ".join(errors))


@dataclass(frozen=True)
class GraphView:
    """Read-only snapshot of graph state for pattern evaluation.

    A minimal graph abstraction that PatternMatcher evaluates against.
    The real GraphBackend (M051) is adapted to this interface by the
    composition layer.

    Fields:
      - vertices: dict of vertex_id -> {type, ...attributes}.
      - edges: list of {kind, source, target, ...attributes}.
    """

    vertices: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: list[dict[str, Any]] = field(default_factory=list)


class PatternMatcher:
    """Evaluates patterns against a GraphView.

    A pattern matches if ALL its clauses are satisfied:
      - EXISTS: at least one vertex of the given type with matching filter exists.
      - NOT_EXISTS: no vertex of the given type with matching filter exists.

    Edge conditions narrow the vertex set: the vertex must have an edge of
    the specified kind to/from a vertex of the specified target type.
    """

    def matches(self, pattern: Pattern, graph: GraphView) -> bool:
        """Check if ALL clauses in the pattern match the graph state."""
        return all(self._clause_matches(clause, graph) for clause in pattern.clauses)

    def find_matching_vertices(
        self, clause: PatternClause, graph: GraphView,
    ) -> list[str]:
        """Find vertices matching a clause's vertex_type + filter."""
        results: list[str] = []
        for vid, vdata in graph.vertices.items():
            if vdata.get("type") != clause.vertex_type:
                continue
            if not self._filter_matches(vdata, clause.filter):
                continue
            # Check edge condition if specified.
            if clause.edge_to and not self._has_edge(vid, clause.edge_to, graph):
                continue
            results.append(vid)
        return results

    def _clause_matches(self, clause: PatternClause, graph: GraphView) -> bool:
        """Check if a single clause matches."""
        matching = self.find_matching_vertices(clause, graph)
        if clause.condition == PatternCondition.EXISTS:
            return len(matching) > 0
        if clause.condition == PatternCondition.NOT_EXISTS:
            return len(matching) == 0
        return False

    def _filter_matches(self, vertex_data: dict[str, Any], filt: dict[str, Any]) -> bool:
        """Check if all filter key-values match vertex attributes."""
        return all(vertex_data.get(k) == v for k, v in filt.items())

    def _has_edge(self, vertex_id: str, edge_spec: dict[str, Any], graph: GraphView) -> bool:
        """Check if vertex has an edge of the specified kind to target_type."""
        kind = edge_spec.get("kind", "")
        target_type = edge_spec.get("target_type", "")
        direction = edge_spec.get("direction", "outgoing")  # outgoing|incoming

        for edge in graph.edges:
            if edge.get("kind") != kind:
                continue
            if direction == "outgoing" and edge.get("source") == vertex_id:
                target_id = edge.get("target", "")
                target = graph.vertices.get(target_id, {})
                if target.get("type") == target_type:
                    return True
            elif direction == "incoming" and edge.get("target") == vertex_id:
                source_id = edge.get("source", "")
                source = graph.vertices.get(source_id, {})
                if source.get("type") == target_type:
                    return True
        return False
