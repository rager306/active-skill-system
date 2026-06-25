"""L2 Application — SQLRepairPolicy (M018 S02).

Maps SQL query plan gaps (``SQLGapClass``) to repair actions
(``SQLActionType``). Mirrors the shape of ``compiler_repair_policy.py``
(M016 S02) but scoped to the SQL profile: 5 gap classes map to 4
action types. Default policy keeps the loop alive (PICK_ALTERNATIVE-style
default actions are forbidden — SQL has no REVERT-style action because
the policy has no prior state to revert to).

The repair policy is intentionally separate from the reasoning-domain
``RepairPolicy`` (different gap/action vocabularies, decoupled
evolution). Decoupling is enforced by a dedicated test.

Pure application. NO infrastructure imports (R002).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from active_skill_system.domain.sql_types import SQLActionType, SQLGapClass


@dataclass(frozen=True)
class SQLRepairPolicy:
    """Maps SQL plan gaps to repair actions.

    Carries:
      - mapping: dict[SQLGapClass, SQLActionType] — non-empty.
    """

    mapping: dict[SQLGapClass, SQLActionType] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.mapping, dict):
            errors.append(f"mapping must be a dict (got {type(self.mapping).__name__})")
        elif not self.mapping:
            errors.append("mapping must be non-empty")
        else:
            for gap, action in self.mapping.items():
                if not isinstance(gap, SQLGapClass):
                    errors.append(f"mapping key must be a SQLGapClass (got {type(gap).__name__})")
                if not isinstance(action, SQLActionType):
                    errors.append(f"mapping value must be a SQLActionType (got {type(action).__name__})")
        if errors:
            raise ValueError("SQLRepairPolicy invariant violation: " + "; ".join(errors))

    def action_for(self, gap: SQLGapClass) -> SQLActionType:
        """Return the action for a gap class, falling back to REPLAN_QUERY.

        REPLAN_QUERY is the safe default because it does not assume prior
        state — the loop can re-plan from scratch instead of trying to
        roll back a transform that may not have been applied.
        """
        return self.mapping.get(gap, SQLActionType.REPLAN_QUERY)

    def covers(self, gap: SQLGapClass) -> bool:
        """True iff this policy has an explicit mapping for ``gap``.

        Useful for EvolutionEngine coverage diagnostics (mirrors
        ``CompilerRepairPolicy.covers``).
        """
        return gap in self.mapping

    @staticmethod
    def default_policy() -> SQLRepairPolicy:
        """Return the default 5->4 mapping for SQL plan gaps.

        Covers every ``SQLGapClass``:
          - MISSING_INDEX -> ADD_INDEX (try adding an index)
          - FULL_TABLE_SCAN -> ADD_INDEX (an index would have prevented the scan)
          - WRONG_JOIN_ORDER -> REORDER_JOINS
          - INEFFICIENT_AGGREGATE -> REWRITE_AS_JOIN (rewrite subquery as JOIN)
          - COST_REGRESSION -> REPLAN_QUERY (start over)

        Cost regression routes to REPLAN_QUERY (not to a "retry" action)
        because the default policy must not loop indefinitely on bad
        candidates — REPLAN_QUERY is the explicit user-facing escape hatch.
        """
        return SQLRepairPolicy(
            mapping={
                SQLGapClass.MISSING_INDEX: SQLActionType.ADD_INDEX,
                SQLGapClass.FULL_TABLE_SCAN: SQLActionType.ADD_INDEX,
                SQLGapClass.WRONG_JOIN_ORDER: SQLActionType.REORDER_JOINS,
                SQLGapClass.INEFFICIENT_AGGREGATE: SQLActionType.REWRITE_AS_JOIN,
                SQLGapClass.COST_REGRESSION: SQLActionType.REPLAN_QUERY,
            },
        )
