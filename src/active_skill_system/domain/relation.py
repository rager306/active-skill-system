"""L1 Domain — Relation + RelationBehavior (M054 S00, Wave D primitive #4).

A Relation is a typed edge between two vertex types. A RelationBehavior is
logic that fires when a relation of a specific kind is created. This mirrors
activegraph's RelationBehavior — edge-level reactivity complementing the
event-level (BehaviorRuntime) and graph-level (PatternMatcher) reactivity.

Wave D primitive #4 (Relations) in our hexagonal architecture.

Pure domain. NO I/O, NO infrastructure imports (R002/R003). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class RelationCardinality:
    """Common edge cardinality constraints for relation validation."""

    ONE_TO_ONE = "1:1"
    ONE_TO_MANY = "1:N"
    MANY_TO_ONE = "N:1"
    MANY_TO_MANY = "N:N"


@dataclass(frozen=True)
class Relation:
    """A typed edge between two vertex types.

    Fields:
      - kind: the edge kind (e.g. "supports", "contradicts", "depends_on").
      - source_type: the source vertex type (e.g. "evidence").
      - target_type: the target vertex type (e.g. "claim").
      - cardinality: RelationCardinality constraint (default MANY_TO_MANY).
      - metadata: optional additional attributes (e.g. {"weight": 0.9}).

    This describes a RELATION TYPE (schema), not a specific edge instance.
    Specific edge instances live in GraphBackend as Edge(kind, src, dst, data).
    """

    kind: str
    source_type: str
    target_type: str
    cardinality: str = RelationCardinality.MANY_TO_MANY
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.kind, str) or not self.kind.strip():
            errors.append(f"kind must be non-empty string (got {self.kind!r})")
        if not isinstance(self.source_type, str) or not self.source_type.strip():
            errors.append(f"source_type must be non-empty string (got {self.source_type!r})")
        if not isinstance(self.target_type, str) or not self.target_type.strip():
            errors.append(f"target_type must be non-empty string (got {self.target_type!r})")
        valid_cardinality = (
            RelationCardinality.ONE_TO_ONE, RelationCardinality.ONE_TO_MANY,
            RelationCardinality.MANY_TO_ONE, RelationCardinality.MANY_TO_MANY,
        )
        if self.cardinality not in valid_cardinality:
            errors.append(
                f"cardinality must be one of {valid_cardinality} (got {self.cardinality!r})"
            )
        if not isinstance(self.metadata, dict):
            errors.append(f"metadata must be dict (got {type(self.metadata).__name__})")
        if errors:
            raise ValueError("Relation invariant violation: " + "; ".join(errors))

    def matches_edge(self, edge_kind: str, source_type: str, target_type: str) -> bool:
        """Check if a specific edge matches this relation type.

        Args:
            edge_kind: the edge's kind.
            source_type: the source vertex's type.
            target_type: the target vertex's type.

        Returns:
            True if all three match.
        """
        return (
            self.kind == edge_kind
            and self.source_type == source_type
            and self.target_type == target_type
        )


@dataclass(frozen=True)
class RelationBehavior:
    """A behavior that fires when a relation of a specific kind is created.

    Fields:
      - name: unique relation behavior identifier.
      - relation: the Relation type that triggers this behavior.
      - description: human-readable purpose.
      - activate_after: minimum edge count before behavior activates.

    The handler is NOT stored here (registered at runtime via
    RelationBehaviorRuntime.register_relation_behavior in S03). This domain
    type describes the SPEC.
    """

    name: str
    relation: Relation
    description: str = ""
    activate_after: int = 0

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.name, str) or not self.name.strip():
            errors.append(f"name must be non-empty string (got {self.name!r})")
        if not isinstance(self.relation, Relation):
            errors.append(f"relation must be a Relation (got {type(self.relation).__name__})")
        if not isinstance(self.activate_after, int) or self.activate_after < 0:
            errors.append(f"activate_after must be non-negative int (got {self.activate_after!r})")
        if not isinstance(self.description, str):
            errors.append(f"description must be string (got {type(self.description).__name__})")
        if errors:
            raise ValueError("RelationBehavior invariant violation: " + "; ".join(errors))

    def matches_edge(self, edge_kind: str, source_type: str, target_type: str) -> bool:
        """Delegate to relation.matches_edge."""
        return self.relation.matches_edge(edge_kind, source_type, target_type)
