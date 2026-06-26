"""Tests for domain/ml_types.py (M027 S01)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from active_skill_system.domain.ml_types import (
    MLActionType,
    MLGapClass,
    MLMetrics,
    MLNodeKind,
    MLTransformParams,
)


def test_ml_node_kind_has_plan_kinds() -> None:
    assert MLNodeKind.LAYER.value == "layer"
    assert MLNodeKind.OPTIMIZER.value == "optimizer"
    assert MLNodeKind.LOSS_FN.value == "loss_fn"
    assert MLNodeKind.DATASET.value == "dataset"


def test_ml_node_kind_has_transform_kinds() -> None:
    assert MLNodeKind.ML_TRANSFORM_ADJUST_LR.value == "ml_transform_adjust_lr"
    assert MLNodeKind.ML_TRANSFORM_PRUNE_LAYER.value == "ml_transform_prune_layer"
    assert MLNodeKind.ML_TRANSFORM_ADD_REGULARIZATION.value == "ml_transform_add_regularization"
    assert MLNodeKind.ML_TRANSFORM_SWITCH_OPTIMIZER.value == "ml_transform_switch_optimizer"


def test_ml_gap_class_has_five_values() -> None:
    assert len(MLGapClass) == 5
    assert MLGapClass.HIGH_LOSS.value == "high_loss"
    assert MLGapClass.OVERFITTING.value == "overfitting"


def test_ml_action_type_has_four_values() -> None:
    assert len(MLActionType) == 4
    assert MLActionType.ADJUST_LR.value == "adjust_lr"
    assert MLActionType.SWITCH_OPTIMIZER.value == "switch_optimizer"


def test_ml_transform_params_accepts_valid_kind() -> None:
    p = MLTransformParams(transform_type=MLNodeKind.ML_TRANSFORM_ADJUST_LR, params={"lr_factor": 0.1}, legal=True)
    assert p.transform_type is MLNodeKind.ML_TRANSFORM_ADJUST_LR


def test_ml_transform_params_rejects_non_transform_kind() -> None:
    with pytest.raises(ValueError, match="ML_TRANSFORM"):
        MLTransformParams(transform_type=MLNodeKind.LAYER, params={}, legal=True)


def test_ml_transform_params_rejects_non_dict_params() -> None:
    with pytest.raises(ValueError, match="params must be a dict"):
        MLTransformParams(transform_type=MLNodeKind.ML_TRANSFORM_ADJUST_LR, params=[1], legal=True)  # type: ignore[arg-type]


def _baseline_metrics(loss: float = 0.5) -> MLMetrics:
    return MLMetrics(loss=loss, accuracy=0.85, epochs=100, convergence_time=3600.0, is_valid=True)


def test_ml_metrics_rejects_negative_loss() -> None:
    with pytest.raises(ValueError, match="loss"):
        MLMetrics(loss=-0.1, accuracy=0.5, epochs=1, convergence_time=1.0)


def test_ml_metrics_rejects_accuracy_out_of_range() -> None:
    with pytest.raises(ValueError, match="accuracy"):
        MLMetrics(loss=0.5, accuracy=1.5, epochs=1, convergence_time=1.0)


def test_ml_metrics_better_than_strictly_lower_loss() -> None:
    base = _baseline_metrics(loss=0.5)
    better = _baseline_metrics(loss=0.3)
    assert better.better_than(base)
    assert not base.better_than(better)


def test_ml_metrics_better_than_tie_break_by_accuracy_higher() -> None:
    """accuracy is inverse axis — higher is better (same loss)."""
    base = MLMetrics(loss=0.5, accuracy=0.85, epochs=100, convergence_time=100.0, is_valid=True)
    better = MLMetrics(loss=0.5, accuracy=0.92, epochs=100, convergence_time=100.0, is_valid=True)
    assert better.better_than(base)


def test_ml_metrics_better_than_tie_break_by_epochs_lower() -> None:
    base = MLMetrics(loss=0.5, accuracy=0.85, epochs=100, convergence_time=100.0, is_valid=True)
    better = MLMetrics(loss=0.5, accuracy=0.85, epochs=50, convergence_time=100.0, is_valid=True)
    assert better.better_than(base)


def test_ml_metrics_invalid_never_beats_valid() -> None:
    valid = _baseline_metrics(loss=10.0)
    invalid = MLMetrics(loss=0.0, accuracy=1.0, epochs=1, convergence_time=0.0, is_valid=False)
    assert not invalid.better_than(valid)
    assert valid.better_than(invalid)


def test_ml_metrics_convergence_time_does_not_affect_ranking() -> None:
    base = MLMetrics(loss=0.5, accuracy=0.85, epochs=100, convergence_time=100.0, is_valid=True)
    same_other = MLMetrics(loss=0.5, accuracy=0.85, epochs=100, convergence_time=9999.0, is_valid=True)
    assert not same_other.better_than(base)
    assert not base.better_than(same_other)


def test_ml_metrics_better_than_handles_invalid_input() -> None:
    m = _baseline_metrics()
    assert not m.better_than("not metrics")  # type: ignore[arg-type]


def test_ml_types_module_infra_free() -> None:
    mod = importlib.import_module("active_skill_system.domain.ml_types")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"ml_types.py must not contain '{forbidden}' (R002)"
