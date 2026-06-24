"""L1 Domain - Gap classification (M009, concept.md §7).

Classifies gaps detected by the validator into typed classes so the repair
loop can choose a bounded action. concept.md §7 gap table:

  Missing evidence   → find source (search, RAG)
  Ambiguity          → create alternative branches
  Missing mechanism  → decompose or find skill
  Contradiction      → compare provenance and trust
  Constraint violation → replan
  Tool failure       → retry or substitute tool
  Undefined concept  → link to ontology or define
  Unsafe action      → request approval

Pure domain. NO I/O, NO infrastructure imports (R002). Frozen dataclasses
with ``__post_init__`` validation. stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from active_skill_system.domain.runtime.nodes import TaskNodeId


class GapClass(StrEnum):
    """Type of a gap (concept.md §7 gap-classes)."""

    MISSING_EVIDENCE = "missing_evidence"
    AMBIGUITY = "ambiguity"
    MISSING_MECHANISM = "missing_mechanism"
    CONTRADICTION = "contradiction"
    CONSTRAINT_VIOLATION = "constraint_violation"
    TOOL_FAILURE = "tool_failure"
    UNDEFINED_CONCEPT = "undefined_concept"
    UNSAFE_ACTION = "unsafe_action"


class Severity(StrEnum):
    """Severity of a gap — drives repair priority."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Priority ordering for repair: critical first.
_SEVERITY_PRIORITY = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


def severity_rank(severity: Severity) -> int:
    """Lower rank = higher priority (critical=0, low=3)."""
    return _SEVERITY_PRIORITY.get(severity, 4)


@dataclass(frozen=True)
class GapClassification:
    """A gap classified by the repair loop.

    Carries:
      - node_id: the TaskNodeId of the gap node (or unsupported goal).
      - gap_class: one of GapClass — drives which repair action is chosen.
      - severity: drives repair priority (critical resolved first).
      - proposed_action: a short human-readable hint (e.g. "search", "replan").
    """

    node_id: TaskNodeId
    gap_class: GapClass
    severity: Severity
    proposed_action: str

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.node_id, TaskNodeId):
            errors.append(
                f"node_id must be a TaskNodeId (got {type(self.node_id).__name__})"
            )
        if not isinstance(self.gap_class, GapClass):
            errors.append(
                f"gap_class must be a GapClass (got {type(self.gap_class).__name__})"
            )
        if not isinstance(self.severity, Severity):
            errors.append(
                f"severity must be a Severity (got {type(self.severity).__name__})"
            )
        if not isinstance(self.proposed_action, str) or not self.proposed_action.strip():
            errors.append(
                f"proposed_action must be a non-empty string (got {self.proposed_action!r})"
            )
        if errors:
            raise ValueError(
                f"GapClassification({self.node_id}) invariant violation: "
                + "; ".join(errors)
            )
