"""L2 Application — IaCRepairPolicy (M023 S02).

Maps IaC plan gaps (``IaCGapClass``) to repair actions (``IaCActionType``).
Mirrors ``compiler_repair_policy.py`` (M016 S02) and ``sql_repair_policy.py``
(M018 S02) shape: 5 gap classes map to 4 action types. Default policy keeps
the loop alive (PICK_ALTERNATIVE-style defaults are forbidden; IaC has no
REVERT-style action because the policy has no prior state to revert to).

The repair policy is intentionally separate from the reasoning-domain
``RepairPolicy``, the compiler ``CompilerRepairPolicy``, and the SQL
``SQLRepairPolicy`` (different gap/action vocabularies, decoupled
evolution). Decoupling is enforced by a dedicated test.

Pure application. NO infrastructure imports (R002).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from active_skill_system.domain.iac_types import IaCActionType, IaCGapClass


@dataclass(frozen=True)
class IaCRepairPolicy:
    """Maps IaC plan gaps to repair actions.

    Carries:
      - mapping: dict[IaCGapClass, IaCActionType] — non-empty.
    """

    mapping: dict[IaCGapClass, IaCActionType] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.mapping, dict):
            errors.append(f"mapping must be a dict (got {type(self.mapping).__name__})")
        elif not self.mapping:
            errors.append("mapping must be non-empty")
        else:
            for gap, action in self.mapping.items():
                if not isinstance(gap, IaCGapClass):
                    errors.append(f"mapping key must be a IaCGapClass (got {type(gap).__name__})")
                if not isinstance(action, IaCActionType):
                    errors.append(f"mapping value must be a IaCActionType (got {type(action).__name__})")
        if errors:
            raise ValueError("IaCRepairPolicy invariant violation: " + "; ".join(errors))

    def action_for(self, gap: IaCGapClass) -> IaCActionType:
        """Return the action for a gap class, falling back to REPLAN_PROVIDERS.

        REPLAN_PROVIDERS is the safe default because it does not assume
        prior state — the loop can re-provision from scratch instead of
        trying to roll back a transform that may not have been applied.
        """
        return self.mapping.get(gap, IaCActionType.REPLAN_PROVIDERS)

    def covers(self, gap: IaCGapClass) -> bool:
        """True iff this policy has an explicit mapping for ``gap``."""
        return gap in self.mapping

    @staticmethod
    def default_policy() -> IaCRepairPolicy:
        """Return the default 5->4 mapping for IaC plan gaps.

        Covers every ``IaCGapClass``:
          - UNUSED_VARIABLE -> REMOVE_UNUSED
          - MISSING_OUTPUT -> ADD_OUTPUT
          - CIRCULAR_DEPENDENCY -> RESTRUCTURE_DEP
          - DRIFT_DETECTED -> REPLAN_PROVIDERS
          - COST_REGRESSION -> REPLAN_PROVIDERS

        Both DRIFT_DETECTED and COST_REGRESSION route to REPLAN_PROVIDERS
        because the default policy must not loop indefinitely on bad
        candidates — REPLAN_PROVIDERS is the user-facing escape hatch.
        """
        return IaCRepairPolicy(
            mapping={
                IaCGapClass.UNUSED_VARIABLE: IaCActionType.REMOVE_UNUSED,
                IaCGapClass.MISSING_OUTPUT: IaCActionType.ADD_OUTPUT,
                IaCGapClass.CIRCULAR_DEPENDENCY: IaCActionType.RESTRUCTURE_DEP,
                IaCGapClass.DRIFT_DETECTED: IaCActionType.REPLAN_PROVIDERS,
                IaCGapClass.COST_REGRESSION: IaCActionType.REPLAN_PROVIDERS,
            },
        )
