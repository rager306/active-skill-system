"""L2 Application use-case — RepairPolicy + ActionType (M009 S02).

Maps a ``GapClass`` (domain) to an ``ActionType`` the repair loop can
execute. The policy is a pure value-object; actual execution (tool calls,
replanning, approval) lives in the repair loop and its action-execution
callback (wired with real tools in S03).

concept.md §7 gap → action table:
  Missing evidence   → search (RAG, DB, API)
  Ambiguity          → clarify (ask user)
  Missing mechanism  → decompose (sub-graph / find skill)
  Contradiction      → replan (compare provenance, rebuild)
  Constraint violation → replan (rebuild Plan Graph)
  Tool failure       → substitute_tool (retry, fallback)
  Undefined concept  → define_concept (link to ontology)
  Unsafe action      → approve (human approval gate)

Pure application. Depends on domain only; no I/O (R002).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from active_skill_system.domain.runtime.gap import GapClass


class ActionType(StrEnum):
    """Type of repair action the loop can execute for a gap."""

    SEARCH = "search"
    REPLAN = "replan"
    CLARIFY = "clarify"
    APPROVE = "approve"
    DECOMPOSE = "decompose"
    SUBSTITUTE_TOOL = "substitute_tool"
    DEFINE_CONCEPT = "define_concept"


# Default mapping (concept.md §7).
_DEFAULT_POLICY: dict[GapClass, ActionType] = {
    GapClass.MISSING_EVIDENCE: ActionType.SEARCH,
    GapClass.AMBIGUITY: ActionType.CLARIFY,
    GapClass.MISSING_MECHANISM: ActionType.DECOMPOSE,
    GapClass.CONTRADICTION: ActionType.REPLAN,
    GapClass.CONSTRAINT_VIOLATION: ActionType.REPLAN,
    GapClass.TOOL_FAILURE: ActionType.SUBSTITUTE_TOOL,
    GapClass.UNDEFINED_CONCEPT: ActionType.DEFINE_CONCEPT,
    GapClass.UNSAFE_ACTION: ActionType.APPROVE,
}


@dataclass(frozen=True)
class RepairPolicy:
    """Maps ``GapClass`` → ``ActionType``. Immutable; injectable.

    Use ``default_policy()`` for the concept.md §7 mapping, or construct
    with a custom dict for testing or domain-specific overrides.
    """

    mapping: dict[GapClass, ActionType]

    def __post_init__(self) -> None:
        if not isinstance(self.mapping, dict) or not self.mapping:
            raise ValueError(
                f"RepairPolicy.mapping must be a non-empty dict (got {self.mapping!r})"
            )

    def action_for(self, gap_class: GapClass) -> ActionType:
        """Return the ActionType for a gap class, or REPLAN as fallback."""
        return self.mapping.get(gap_class, ActionType.REPLAN)

    @classmethod
    def default_policy(cls) -> RepairPolicy:
        """concept.md §7 default gap→action mapping."""
        return cls(mapping=dict(_DEFAULT_POLICY))
