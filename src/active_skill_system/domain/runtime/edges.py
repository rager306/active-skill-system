"""L1 Domain - Task Graph edges (Cognitive Runtime bounded context).

Edge kinds for the reasoning structure (concept.md §4.1 relation table).
A TaskEdge connects two existing nodes by a typed relation.

Pure domain. NO I/O, NO infrastructure imports (R002). Frozen dataclass with
``__post_init__`` invariant validation. stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from active_skill_system.domain.runtime.nodes import TaskNodeId


class EdgeKind(StrEnum):
    """Typed relation between two Task Graph nodes (concept.md §4.1)."""

    SUPPORTS = "supports"  # evidence/claim supports a goal/claim
    REQUIRES = "requires"  # goal requires a sub-goal/evidence
    DERIVED_FROM = "derived_from"  # claim derived from evidence/mechanism
    CAUSES = "causes"
    CONTRADICTS = "contradicts"  # claim contradicts another claim
    BLOCKS = "blocks"  # gap blocks a goal
    SATISFIES = "satisfies"  # evidence/result satisfies a constraint/goal
    REFINES = "refines"
    DEPENDS_ON = "depends_on"
    PRODUCES = "produces"  # action produces a result
    INVALIDATES = "invalidates"  # new evidence invalidates a claim


@dataclass(frozen=True)
class TaskEdge:
    """A typed relation between two Task Graph nodes.

    Carries:
      - source: the origin node id (TaskNodeId).
      - target: the destination node id (TaskNodeId).
      - kind: one of EdgeKind.

    Invariants:
      - source != target (no self-loops; they add noise, not signal).
      - both ids are TaskNodeId instances.
    """

    source: TaskNodeId
    target: TaskNodeId
    kind: EdgeKind

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.source, TaskNodeId):
            errors.append(f"source must be a TaskNodeId (got {type(self.source).__name__})")
        if not isinstance(self.target, TaskNodeId):
            errors.append(f"target must be a TaskNodeId (got {type(self.target).__name__})")
        if not isinstance(self.kind, EdgeKind):
            errors.append(f"kind must be an EdgeKind (got {type(self.kind).__name__})")
        if isinstance(self.source, TaskNodeId) and isinstance(self.target, TaskNodeId) and self.source.value == self.target.value:
            errors.append(f"self-loop forbidden: source == target ({self.source})")
        if errors:
            raise ValueError("TaskEdge invariant violation: " + "; ".join(errors))
