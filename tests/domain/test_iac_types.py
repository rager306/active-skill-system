"""Tests for domain/iac_types.py (M023 S01)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from active_skill_system.domain.iac_types import (
    IaCActionType,
    IaCGapClass,
    IaCNodeKind,
    IaCPlanMetrics,
    IaCTransformParams,
)

# ── IaCNodeKind ───────────────────────────────────────────────────────────


def test_iac_node_kind_has_plan_kinds() -> None:
    assert IaCNodeKind.RESOURCE.value == "resource"
    assert IaCNodeKind.MODULE.value == "module"
    assert IaCNodeKind.VARIABLE.value == "variable"
    assert IaCNodeKind.OUTPUT.value == "output"
    assert IaCNodeKind.PROVIDER.value == "provider"


def test_iac_node_kind_has_transform_kinds() -> None:
    assert IaCNodeKind.IA_TRANSFORM_REMOVE_UNUSED.value == "ia_transform_remove_unused"
    assert IaCNodeKind.IA_TRANSFORM_ADD_OUTPUT.value == "ia_transform_add_output"
    assert IaCNodeKind.IA_TRANSFORM_RESTRUCTURE_DEP.value == "ia_transform_restructure_dep"
    assert IaCNodeKind.IA_TRANSFORM_REPLAN_PROVIDERS.value == "ia_transform_replan_providers"


# ── IaCGapClass ──────────────────────────────────────────────────────────


def test_iac_gap_class_has_five_values() -> None:
    assert len(IaCGapClass) == 5
    assert IaCGapClass.UNUSED_VARIABLE.value == "unused_variable"
    assert IaCGapClass.MISSING_OUTPUT.value == "missing_output"
    assert IaCGapClass.CIRCULAR_DEPENDENCY.value == "circular_dependency"
    assert IaCGapClass.DRIFT_DETECTED.value == "drift_detected"
    assert IaCGapClass.COST_REGRESSION.value == "cost_regression"


# ── IaCActionType ────────────────────────────────────────────────────────


def test_iac_action_type_has_four_values() -> None:
    assert len(IaCActionType) == 4
    assert IaCActionType.REMOVE_UNUSED.value == "remove_unused"
    assert IaCActionType.ADD_OUTPUT.value == "add_output"
    assert IaCActionType.RESTRUCTURE_DEP.value == "restructure_dep"
    assert IaCActionType.REPLAN_PROVIDERS.value == "replan_providers"


# ── IaCTransformParams ───────────────────────────────────────────────────


def _remove_unused(variable_name: str = "old_var") -> IaCTransformParams:
    return IaCTransformParams(
        transform_type=IaCNodeKind.IA_TRANSFORM_REMOVE_UNUSED,
        params={"variable_name": variable_name},
        legal=True,
    )


def test_iac_transform_params_accepts_valid_kind() -> None:
    p = _remove_unused()
    assert p.transform_type is IaCNodeKind.IA_TRANSFORM_REMOVE_UNUSED


def test_iac_transform_params_rejects_non_transform_kind() -> None:
    with pytest.raises(ValueError, match="IA_TRANSFORM"):
        IaCTransformParams(
            transform_type=IaCNodeKind.RESOURCE,
            params={},
            legal=True,
        )


def test_iac_transform_params_rejects_non_dict_params() -> None:
    with pytest.raises(ValueError, match="params must be a dict"):
        IaCTransformParams(
            transform_type=IaCNodeKind.IA_TRANSFORM_REMOVE_UNUSED,
            params=["not", "a", "dict"],  # type: ignore[arg-type]
            legal=True,
        )


def test_iac_transform_params_rejects_non_bool_legal() -> None:
    with pytest.raises(ValueError, match="legal must be a bool"):
        IaCTransformParams(
            transform_type=IaCNodeKind.IA_TRANSFORM_REMOVE_UNUSED,
            params={},
            legal="yes",  # type: ignore[arg-type]
        )


# ── IaCPlanMetrics ───────────────────────────────────────────────────────


def _baseline_metrics(resources: int = 100) -> IaCPlanMetrics:
    return IaCPlanMetrics(
        resource_count=resources, module_count=10, variable_count=20, drift_score=0.5, is_valid=True,
    )


def test_iac_plan_metrics_rejects_negative_resource_count() -> None:
    with pytest.raises(ValueError, match="resource_count"):
        IaCPlanMetrics(resource_count=-1, module_count=0, variable_count=0, drift_score=0.0)


def test_iac_plan_metrics_rejects_negative_drift_score() -> None:
    with pytest.raises(ValueError, match="drift_score"):
        IaCPlanMetrics(resource_count=1, module_count=1, variable_count=1, drift_score=-0.1)


def test_iac_plan_metrics_rejects_non_bool_is_valid() -> None:
    with pytest.raises(ValueError, match="is_valid"):
        IaCPlanMetrics(resource_count=0, module_count=0, variable_count=0, drift_score=0.0, is_valid=1)  # type: ignore[arg-type]


def test_iac_plan_metrics_better_than_strictly_lower_resource_count() -> None:
    base = _baseline_metrics(resources=100)
    better = _baseline_metrics(resources=50)
    assert better.better_than(base)
    assert not base.better_than(better)


def test_iac_plan_metrics_better_than_tie_break_by_variable_count() -> None:
    base = IaCPlanMetrics(resource_count=100, module_count=10, variable_count=20, drift_score=0.5, is_valid=True)
    better = IaCPlanMetrics(resource_count=100, module_count=10, variable_count=10, drift_score=0.5, is_valid=True)
    assert better.better_than(base)


def test_iac_plan_metrics_better_than_tie_break_by_drift_score() -> None:
    base = IaCPlanMetrics(resource_count=100, module_count=10, variable_count=20, drift_score=0.5, is_valid=True)
    better = IaCPlanMetrics(resource_count=100, module_count=10, variable_count=20, drift_score=0.2, is_valid=True)
    assert better.better_than(base)


def test_iac_plan_metrics_invalid_never_beats_valid() -> None:
    valid = _baseline_metrics(resources=10000)
    invalid = IaCPlanMetrics(resource_count=1, module_count=1, variable_count=1, drift_score=0.0, is_valid=False)
    assert not invalid.better_than(valid)
    assert valid.better_than(invalid)


def test_iac_plan_metrics_module_count_does_not_affect_ranking() -> None:
    """module_count is reported but not in the ranking (side diagnostic)."""
    base = IaCPlanMetrics(resource_count=100, module_count=10, variable_count=20, drift_score=0.5, is_valid=True)
    worse_modules = IaCPlanMetrics(resource_count=100, module_count=999, variable_count=20, drift_score=0.5, is_valid=True)
    assert not worse_modules.better_than(base)
    assert not base.better_than(worse_modules)


def test_iac_plan_metrics_better_than_handles_invalid_input() -> None:
    m = _baseline_metrics()
    assert not m.better_than("not metrics")  # type: ignore[arg-type]


# ── R002 ────────────────────────────────────────────────────────────────


def test_iac_types_module_infra_free() -> None:
    mod = importlib.import_module("active_skill_system.domain.iac_types")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"iac_types.py must not contain '{forbidden}' (R002)"
