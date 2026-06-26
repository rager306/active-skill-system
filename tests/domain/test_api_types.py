"""Tests for domain/api_types.py (M031 S01)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from active_skill_system.domain.api_types import (
    APIActionType,
    APIGapClass,
    APIMetrics,
    APINodeKind,
    APITransformParams,
)


def test_api_node_kind_has_plan_kinds() -> None:
    assert APINodeKind.ENDPOINT.value == "endpoint"
    assert APINodeKind.RATE_LIMITER.value == "rate_limiter"
    assert APINodeKind.QUOTA.value == "quota"
    assert APINodeKind.THROTTLE.value == "throttle"


def test_api_node_kind_has_transform_kinds() -> None:
    assert APINodeKind.API_TRANSFORM_INCREASE_QUOTA.value == "api_transform_increase_quota"
    assert APINodeKind.API_TRANSFORM_CACHE.value == "api_transform_cache"
    assert APINodeKind.API_TRANSFORM_BATCH.value == "api_transform_batch"
    assert APINodeKind.API_TRANSFORM_DEBOUNCE.value == "api_transform_debounce"


def test_api_gap_class_has_five_values() -> None:
    assert len(APIGapClass) == 5
    assert APIGapClass.HIGH_UTILIZATION.value == "high_utilization"
    assert APIGapClass.QUOTA_EXHAUSTION.value == "quota_exhaustion"


def test_api_action_type_has_four_values() -> None:
    assert len(APIActionType) == 4
    assert APIActionType.INCREASE_QUOTA.value == "increase_quota"
    assert APIActionType.DEBOUNCE.value == "debounce"


def test_api_transform_params_accepts_valid_kind() -> None:
    p = APITransformParams(transform_type=APINodeKind.API_TRANSFORM_CACHE, params={"ttl_seconds": 300}, legal=True)
    assert p.transform_type is APINodeKind.API_TRANSFORM_CACHE


def test_api_transform_params_rejects_non_transform_kind() -> None:
    with pytest.raises(ValueError, match="API_TRANSFORM"):
        APITransformParams(transform_type=APINodeKind.ENDPOINT, params={}, legal=True)


def test_api_transform_params_rejects_non_dict_params() -> None:
    with pytest.raises(ValueError, match="params must be a dict"):
        APITransformParams(transform_type=APINodeKind.API_TRANSFORM_CACHE, params=[1], legal=True)  # type: ignore[arg-type]


def _baseline_metrics(utilization: float = 0.9) -> APIMetrics:
    return APIMetrics(rate_limit_utilization=utilization, throttled_requests_pct=5.0, avg_response_ms=200.0, is_valid=True)


def test_api_metrics_rejects_utilization_out_of_range() -> None:
    with pytest.raises(ValueError, match="rate_limit_utilization"):
        APIMetrics(rate_limit_utilization=1.5, throttled_requests_pct=0.0, avg_response_ms=0.0)


def test_api_metrics_better_than_strictly_lower_utilization() -> None:
    base = _baseline_metrics(utilization=0.9)
    better = _baseline_metrics(utilization=0.5)
    assert better.better_than(base)
    assert not base.better_than(better)


def test_api_metrics_better_than_tie_break_by_throttled_requests() -> None:
    base = APIMetrics(rate_limit_utilization=0.5, throttled_requests_pct=5.0, avg_response_ms=200.0, is_valid=True)
    better = APIMetrics(rate_limit_utilization=0.5, throttled_requests_pct=1.0, avg_response_ms=200.0, is_valid=True)
    assert better.better_than(base)


def test_api_metrics_invalid_never_beats_valid() -> None:
    valid = _baseline_metrics(utilization=0.99)
    invalid = APIMetrics(rate_limit_utilization=0.0, throttled_requests_pct=0.0, avg_response_ms=0.0, is_valid=False)
    assert not invalid.better_than(valid)
    assert valid.better_than(invalid)


def test_api_metrics_avg_response_does_not_affect_ranking() -> None:
    base = APIMetrics(rate_limit_utilization=0.5, throttled_requests_pct=1.0, avg_response_ms=200.0, is_valid=True)
    same_other = APIMetrics(rate_limit_utilization=0.5, throttled_requests_pct=1.0, avg_response_ms=999.0, is_valid=True)
    assert not same_other.better_than(base)


def test_api_metrics_better_than_handles_invalid_input() -> None:
    m = _baseline_metrics()
    assert not m.better_than("not metrics")  # type: ignore[arg-type]


def test_api_types_module_infra_free() -> None:
    mod = importlib.import_module("active_skill_system.domain.api_types")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"api_types.py must not contain '{forbidden}' (R002)"
