"""Tests for domain/log_types.py (M030 S01)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from active_skill_system.domain.log_types import (
    LogActionType,
    LogGapClass,
    LogMetrics,
    LogNodeKind,
    LogTransformParams,
)


def test_log_node_kind_has_plan_kinds() -> None:
    assert LogNodeKind.LOG_ENTRY.value == "log_entry"
    assert LogNodeKind.ERROR.value == "error"
    assert LogNodeKind.WARNING.value == "warning"
    assert LogNodeKind.METRIC.value == "metric"


def test_log_node_kind_has_transform_kinds() -> None:
    assert LogNodeKind.LOG_TRANSFORM_FILTER.value == "log_transform_filter"
    assert LogNodeKind.LOG_TRANSFORM_AGGREGATE.value == "log_transform_aggregate"
    assert LogNodeKind.LOG_TRANSFORM_SAMPLE.value == "log_transform_sample"
    assert LogNodeKind.LOG_TRANSFORM_ROTATE.value == "log_transform_rotate"


def test_log_gap_class_has_five_values() -> None:
    assert len(LogGapClass) == 5
    assert LogGapClass.HIGH_ERROR_RATE.value == "high_error_rate"
    assert LogGapClass.LOG_BLOAT.value == "log_bloat"


def test_log_action_type_has_four_values() -> None:
    assert len(LogActionType) == 4
    assert LogActionType.FILTER.value == "filter"
    assert LogActionType.ROTATE.value == "rotate"


def test_log_transform_params_accepts_valid_kind() -> None:
    p = LogTransformParams(transform_type=LogNodeKind.LOG_TRANSFORM_FILTER, params={"level": "ERROR"}, legal=True)
    assert p.transform_type is LogNodeKind.LOG_TRANSFORM_FILTER


def test_log_transform_params_rejects_non_transform_kind() -> None:
    with pytest.raises(ValueError, match="LOG_TRANSFORM"):
        LogTransformParams(transform_type=LogNodeKind.LOG_ENTRY, params={}, legal=True)


def test_log_transform_params_rejects_non_dict_params() -> None:
    with pytest.raises(ValueError, match="params must be a dict"):
        LogTransformParams(transform_type=LogNodeKind.LOG_TRANSFORM_FILTER, params=[1], legal=True)  # type: ignore[arg-type]


def _baseline_metrics(error_rate: float = 0.1) -> LogMetrics:
    return LogMetrics(error_rate=error_rate, log_volume_mb=500.0, parse_time_ms=1000.0, is_valid=True)


def test_log_metrics_rejects_error_rate_out_of_range() -> None:
    with pytest.raises(ValueError, match="error_rate"):
        LogMetrics(error_rate=1.5, log_volume_mb=100.0, parse_time_ms=100.0)


def test_log_metrics_better_than_strictly_lower_error_rate() -> None:
    base = _baseline_metrics(error_rate=0.1)
    better = _baseline_metrics(error_rate=0.05)
    assert better.better_than(base)
    assert not base.better_than(better)


def test_log_metrics_better_than_tie_break_by_log_volume() -> None:
    base = LogMetrics(error_rate=0.1, log_volume_mb=500.0, parse_time_ms=1000.0, is_valid=True)
    better = LogMetrics(error_rate=0.1, log_volume_mb=200.0, parse_time_ms=1000.0, is_valid=True)
    assert better.better_than(base)


def test_log_metrics_invalid_never_beats_valid() -> None:
    valid = _baseline_metrics(error_rate=0.99)
    invalid = LogMetrics(error_rate=0.0, log_volume_mb=0.0, parse_time_ms=0.0, is_valid=False)
    assert not invalid.better_than(valid)
    assert valid.better_than(invalid)


def test_log_metrics_parse_time_does_not_affect_ranking() -> None:
    base = LogMetrics(error_rate=0.1, log_volume_mb=500.0, parse_time_ms=1000.0, is_valid=True)
    same_other = LogMetrics(error_rate=0.1, log_volume_mb=500.0, parse_time_ms=9999.0, is_valid=True)
    assert not same_other.better_than(base)


def test_log_metrics_better_than_handles_invalid_input() -> None:
    m = _baseline_metrics()
    assert not m.better_than("not metrics")  # type: ignore[arg-type]


def test_log_types_module_infra_free() -> None:
    mod = importlib.import_module("active_skill_system.domain.log_types")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"log_types.py must not contain '{forbidden}' (R002)"
