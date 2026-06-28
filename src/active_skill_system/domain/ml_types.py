"""L1 Domain — ML training loop optimization types (M027 S01).

Domain profile for ML training loop optimization. Mirrors compiler/SQL/IaC/security
types shape. Primary fitness axis: loss (lower = better). Inverse-axis tie-breaker:
accuracy (higher = better). Dual-axis ranking pattern (mirrors SecurityMetrics
coverage_ratio as inverse axis).

Pure domain. NO I/O, NO infrastructure imports (R002). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class MLNodeKind(StrEnum):
    """MLNodeKind class."""
    LAYER = "layer"
    OPTIMIZER = "optimizer"
    LOSS_FN = "loss_fn"
    DATASET = "dataset"
    ML_TRANSFORM_ADJUST_LR = "ml_transform_adjust_lr"
    ML_TRANSFORM_PRUNE_LAYER = "ml_transform_prune_layer"
    ML_TRANSFORM_ADD_REGULARIZATION = "ml_transform_add_regularization"
    ML_TRANSFORM_SWITCH_OPTIMIZER = "ml_transform_switch_optimizer"


class MLGapClass(StrEnum):
    """MLGapClass class."""
    HIGH_LOSS = "high_loss"
    LOW_ACCURACY = "low_accuracy"
    SLOW_CONVERGENCE = "slow_convergence"
    OVERFITTING = "overfitting"
    TRAINING_INSTABILITY = "training_instability"


class MLActionType(StrEnum):
    """MLActionType class."""
    ADJUST_LR = "adjust_lr"
    PRUNE_LAYER = "prune_layer"
    ADD_REGULARIZATION = "add_regularization"
    SWITCH_OPTIMIZER = "switch_optimizer"


@dataclass(frozen=True)
class MLTransformParams:
    """MLTransformParams class."""
    transform_type: MLNodeKind
    params: dict[str, Any]
    legal: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.transform_type, MLNodeKind):
            errors.append(f"transform_type must be a MLNodeKind (got {type(self.transform_type).__name__})")
        transform_kinds = {
            MLNodeKind.ML_TRANSFORM_ADJUST_LR,
            MLNodeKind.ML_TRANSFORM_PRUNE_LAYER,
            MLNodeKind.ML_TRANSFORM_ADD_REGULARIZATION,
            MLNodeKind.ML_TRANSFORM_SWITCH_OPTIMIZER,
        }
        if self.transform_type not in transform_kinds:
            errors.append(f"transform_type must be a ML_TRANSFORM_* kind (got {self.transform_type!r})")
        if not isinstance(self.params, dict):
            errors.append(f"params must be a dict (got {type(self.params).__name__})")
        if not isinstance(self.legal, bool):
            errors.append(f"legal must be a bool (got {type(self.legal).__name__})")
        if errors:
            raise ValueError("MLTransformParams invariant violation: " + "; ".join(errors))


@dataclass(frozen=True)
class MLMetrics:
    """Measured ML training metrics. loss primary (lower=better), accuracy inverse (higher=better).

    Carries:
      - loss: training loss (float, >= 0.0; lower = better).
      - accuracy: validation accuracy (float in [0, 1]; higher = better).
      - epochs: total epochs run (int, >= 0; lower = better for same quality).
      - convergence_time: wall-clock time in seconds (float, >= 0.0; reported but not in ranking).
      - is_valid: False if the training run is invalid.
    """

    loss: float
    accuracy: float
    epochs: int
    convergence_time: float
    is_valid: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.loss, (int, float)) or isinstance(self.loss, bool) or float(self.loss) < 0.0:
            errors.append(f"loss must be a non-negative number (got {self.loss!r})")
        if not isinstance(self.accuracy, (int, float)) or isinstance(self.accuracy, bool) or not (0.0 <= float(self.accuracy) <= 1.0):
            errors.append(f"accuracy must be in [0.0, 1.0] (got {self.accuracy!r})")
        if not isinstance(self.epochs, int) or isinstance(self.epochs, bool) or self.epochs < 0:
            errors.append(f"epochs must be a non-negative int (got {self.epochs!r})")
        if not isinstance(self.convergence_time, (int, float)) or isinstance(self.convergence_time, bool) or float(self.convergence_time) < 0.0:
            errors.append(f"convergence_time must be a non-negative number (got {self.convergence_time!r})")
        if not isinstance(self.is_valid, bool):
            errors.append(f"is_valid must be a bool (got {type(self.is_valid).__name__})")
        if errors:
            raise ValueError("MLMetrics invariant violation: " + "; ".join(errors))

    def better_than(self, other: MLMetrics) -> bool:
        """True if this metrics is strictly better than other.

        Invalid never beats valid. Among valid: strictly lower loss wins,
        OR same loss with strictly higher accuracy (inverse axis),
        OR same loss+accuracy with strictly fewer epochs.
        convergence_time is reported but not in the ranking.
        """
        if not isinstance(other, MLMetrics):
            return False
        if not self.is_valid and other.is_valid:
            return False
        if self.is_valid and not other.is_valid:
            return True
        if float(self.loss) < float(other.loss):
            return True
        if float(self.loss) == float(other.loss):
            if float(self.accuracy) > float(other.accuracy):
                return True
            if float(self.accuracy) == float(other.accuracy) and self.epochs < other.epochs:
                return True
        return False
