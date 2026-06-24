"""L1 Domain - Task Graph nodes (Cognitive Runtime bounded context).

Node kinds for the reasoning structure (concept.md §4.1, architecture.md §4.5):
Goal, Fact, Evidence, Constraint, Hypothesis, Gap, Mechanism, Claim, Decision,
Action, Result.

Pure domain. NO I/O, NO infrastructure imports (R002). Frozen dataclasses with
``__post_init__`` invariant validation. Depends only on stdlib + typing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class NodeKind(StrEnum):
    """Kind of a Task Graph node (concept.md §4.1 node-type table)."""

    GOAL = "goal"
    FACT = "fact"
    EVIDENCE = "evidence"
    CONSTRAINT = "constraint"
    HYPOTHESIS = "hypothesis"
    GAP = "gap"
    MECHANISM = "mechanism"
    CLAIM = "claim"
    DECISION = "decision"
    ACTION = "action"
    RESULT = "result"


@dataclass(frozen=True)
class TaskNodeId:
    """Identifier for a Task Graph node. Wraps a non-empty string."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError(f"TaskNodeId.value must be a non-empty string (got {self.value!r})")

    def __str__(self) -> str:
        return self.value


def _id_non_empty(node: TaskNode) -> None:
    # TaskNodeId already validates on construction; guard against None/missing.
    if not isinstance(node.id, TaskNodeId):
        raise ValueError(f"TaskNode.id must be a TaskNodeId (got {type(node.id).__name__})")


def _kind_valid(node: TaskNode) -> None:
    if not isinstance(node.kind, NodeKind):
        raise ValueError(f"TaskNode.kind must be a NodeKind (got {type(node.kind).__name__})")


def _text_non_empty_for_factual(node: TaskNode) -> None:
    """Goal/Fact/Constraint/Claim/Hypothesis must carry non-empty text.

    Gap/Evidence may have empty text (a Gap is a placeholder; Evidence may be
    described only by its provenance elsewhere).
    """
    _TEXT_REQUIRED = {
        NodeKind.GOAL,
        NodeKind.FACT,
        NodeKind.CONSTRAINT,
        NodeKind.CLAIM,
        NodeKind.HYPOTHESIS,
        NodeKind.MECHANISM,
        NodeKind.DECISION,
        NodeKind.ACTION,
        NodeKind.RESULT,
    }
    if node.kind in _TEXT_REQUIRED and (not isinstance(node.text, str) or not node.text.strip()):
        raise ValueError(
            f"TaskNode({node.id}) of kind {node.kind} requires non-empty text "
            f"(got {node.text!r})"
        )


@dataclass(frozen=True)
class TaskNode:
    """A node in the Task Graph reasoning structure.

    Carries:
      - id: unique identifier (TaskNodeId).
      - kind: one of NodeKind.
      - text: human-readable content (non-empty for factual kinds).
      - created_at: UTC timestamp (tz-aware).
      - meta: frozen mapping of extra attributes (optional).
    """

    id: TaskNodeId
    kind: NodeKind
    text: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    meta: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        errors: list[str] = []
        for check in (_id_non_empty, _kind_valid, _text_non_empty_for_factual):
            try:
                check(self)
            except ValueError as e:
                errors.append(str(e))
        if errors:
            raise ValueError(
                f"TaskNode({getattr(self.id, 'value', self.id)}) invariant violation: "
                + "; ".join(errors)
            )
