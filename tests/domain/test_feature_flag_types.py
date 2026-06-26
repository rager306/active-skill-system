"""Tests for domain/feature_flag_types.py (M036 S01)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from active_skill_system.domain.feature_flag_types import (
    FeatureFlagActionType,
    FeatureFlagMetrics,
    FeatureFlagTransformParams,
    FeatureGapClass,
    FeatureNodeKind,
)


def test_feature_node_kind_has_plan_kinds() -> None:
    assert FeatureNodeKind.FLAG.value == "flag"
    assert FeatureNodeKind.ROLLOUT.value == "rollout"
    assert FeatureNodeKind.SEGMENT.value == "segment"
    assert FeatureNodeKind.VARIANT.value == "variant"


def test_feature_node_kind_has_transform_kinds() -> None:
    assert FeatureNodeKind.FLAG_TRANSFORM_REMOVE_STALE.value == "flag_transform_remove_stale"
    assert FeatureNodeKind.FLAG_TRANSFORM_EXPAND_ROLLOUT.value == "flag_transform_expand_rollout"
    assert FeatureNodeKind.FLAG_TRANSFORM_REDUCE_BLAST.value == "flag_transform_reduce_blast"
    assert FeatureNodeKind.FLAG_TRANSFORM_SPLIT_VARIANT.value == "flag_transform_split_variant"


def test_feature_gap_class_has_five_values() -> None:
    assert len(FeatureGapClass) == 5
    assert FeatureGapClass.STALE_FLAG.value == "stale_flag"
    assert FeatureGapClass.HIGH_BLAST_RADIUS.value == "high_blast_radius"


def test_feature_flag_action_type_has_four_values() -> None:
    assert len(FeatureFlagActionType) == 4
    assert FeatureFlagActionType.REMOVE_STALE.value == "remove_stale"
    assert FeatureFlagActionType.EXPAND_ROLLOUT.value == "expand_rollout"


def test_feature_flag_transform_params_accepts_valid_kind() -> None:
    p = FeatureFlagTransformParams(
        transform_type=FeatureNodeKind.FLAG_TRANSFORM_EXPAND_ROLLOUT,
        params={"new_pct": 50}, legal=True,
    )
    assert p.transform_type is FeatureNodeKind.FLAG_TRANSFORM_EXPAND_ROLLOUT


def test_feature_flag_transform_params_rejects_non_transform_kind() -> None:
    with pytest.raises(ValueError, match="FLAG_TRANSFORM"):
        FeatureFlagTransformParams(
            transform_type=FeatureNodeKind.FLAG, params={}, legal=True,
        )


def test_feature_flag_transform_params_rejects_non_dict_params() -> None:
    with pytest.raises(ValueError, match="params must be a dict"):
        FeatureFlagTransformParams(
            transform_type=FeatureNodeKind.FLAG_TRANSFORM_EXPAND_ROLLOUT,
            params=[1], legal=True,  # type: ignore[arg-type]
        )


def _baseline_metrics(active: int = 10) -> FeatureFlagMetrics:
    return FeatureFlagMetrics(
        active_flags=active, stale_flags=5, rollout_coverage=0.6, blast_radius=1000, is_valid=True,
    )


def test_feature_flag_metrics_rejects_negative_active_flags() -> None:
    with pytest.raises(ValueError, match="active_flags"):
        FeatureFlagMetrics(active_flags=-1, stale_flags=0, rollout_coverage=0.0, blast_radius=0)


def test_feature_flag_metrics_rejects_rollout_coverage_out_of_range() -> None:
    with pytest.raises(ValueError, match="rollout_coverage"):
        FeatureFlagMetrics(active_flags=0, stale_flags=0, rollout_coverage=1.5, blast_radius=0)


def test_feature_flag_metrics_rejects_negative_blast_radius() -> None:
    with pytest.raises(ValueError, match="blast_radius"):
        FeatureFlagMetrics(active_flags=0, stale_flags=0, rollout_coverage=0.0, blast_radius=-1)


def test_feature_flag_metrics_better_than_strictly_higher_active() -> None:
    """active_flags is INVERSE — higher is better (more flags actively used = more value)."""
    base = _baseline_metrics(active=10)
    better = _baseline_metrics(active=20)
    assert better.better_than(base)
    assert not base.better_than(better)


def test_feature_flag_metrics_better_than_tie_break_by_higher_coverage() -> None:
    """rollout_coverage is INVERSE — higher is better (more users exposed)."""
    base = FeatureFlagMetrics(active_flags=10, stale_flags=5, rollout_coverage=0.6, blast_radius=1000, is_valid=True)
    better = FeatureFlagMetrics(active_flags=10, stale_flags=5, rollout_coverage=0.8, blast_radius=1000, is_valid=True)
    assert better.better_than(base)


def test_feature_flag_metrics_better_than_tie_break_by_lower_stale() -> None:
    base = FeatureFlagMetrics(active_flags=10, stale_flags=5, rollout_coverage=0.6, blast_radius=1000, is_valid=True)
    better = FeatureFlagMetrics(active_flags=10, stale_flags=5, rollout_coverage=0.6, blast_radius=1000, is_valid=True)
    # Same active, coverage; better has lower stale
    better_low_stale = FeatureFlagMetrics(active_flags=10, stale_flags=2, rollout_coverage=0.6, blast_radius=1000, is_valid=True)
    assert better_low_stale.better_than(base)


def test_feature_flag_metrics_invalid_never_beats_valid() -> None:
    valid = _baseline_metrics(active=10)
    invalid = FeatureFlagMetrics(active_flags=1000, stale_flags=0, rollout_coverage=1.0, blast_radius=0, is_valid=False)
    assert not invalid.better_than(valid)
    assert valid.better_than(invalid)


def test_feature_flag_metrics_better_than_handles_invalid_input() -> None:
    m = _baseline_metrics()
    assert not m.better_than("not metrics")  # type: ignore[arg-type]


def test_feature_flag_metrics_active_is_inverse_axis() -> None:
    """Documentation invariant: active_flags primary axis is INVERSE (higher = better).

    This is one of the few domains where the primary axis is INVERSE — more
    active flags is better (more value extracted from the flag system).
    """
    low_active = _baseline_metrics(active=5)
    high_active = _baseline_metrics(active=100)
    # higher active_flags should be "better" per better_than.
    assert high_active.better_than(low_active)
    assert not low_active.better_than(high_active)


def test_feature_flag_types_module_infra_free() -> None:
    mod = importlib.import_module("active_skill_system.domain.feature_flag_types")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"feature_flag_types.py must not contain '{forbidden}' (R002)"
