"""L2 Application — MLRepairPolicy (M027 S02).

Maps ML training gaps to repair actions. Default 5→4 mapping.
SWITCH_OPTIMIZER fallback (most aggressive corrective action).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from active_skill_system.domain.ml_types import MLActionType, MLGapClass


@dataclass(frozen=True)
class MLRepairPolicy:
    mapping: dict[MLGapClass, MLActionType] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.mapping, dict):
            errors.append(f"mapping must be a dict (got {type(self.mapping).__name__})")
        elif not self.mapping:
            errors.append("mapping must be non-empty")
        else:
            for gap, action in self.mapping.items():
                if not isinstance(gap, MLGapClass):
                    errors.append(f"mapping key must be a MLGapClass (got {type(gap).__name__})")
                if not isinstance(action, MLActionType):
                    errors.append(f"mapping value must be a MLActionType (got {type(action).__name__})")
        if errors:
            raise ValueError("MLRepairPolicy invariant violation: " + "; ".join(errors))

    def action_for(self, gap: MLGapClass) -> MLActionType:
        return self.mapping.get(gap, MLActionType.SWITCH_OPTIMIZER)

    def covers(self, gap: MLGapClass) -> bool:
        return gap in self.mapping

    @staticmethod
    def default_policy() -> MLRepairPolicy:
        return MLRepairPolicy(mapping={
            MLGapClass.HIGH_LOSS: MLActionType.ADJUST_LR,
            MLGapClass.LOW_ACCURACY: MLActionType.ADD_REGULARIZATION,
            MLGapClass.SLOW_CONVERGENCE: MLActionType.SWITCH_OPTIMIZER,
            MLGapClass.OVERFITTING: MLActionType.ADD_REGULARIZATION,
            MLGapClass.TRAINING_INSTABILITY: MLActionType.SWITCH_OPTIMIZER,
        })
