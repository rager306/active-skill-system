"""Tests for sql_gap_detector (M018 S03)."""

from __future__ import annotations

import importlib
from pathlib import Path

from active_skill_system.application.use_cases.sql_gap_detector import (
    NO_GAP,
    classify_sql_gap,
    is_sql_improved,
)
from active_skill_system.domain.sql_types import SQLGapClass, SQLMetrics


def _m(rows_examined: int = 1000, rows_returned: int = 10, is_valid: bool = True) -> SQLMetrics:
    return SQLMetrics(
        rows_examined=rows_examined, rows_returned=rows_returned,
        time_ms=100.0, plan_cost=50.0, is_valid=is_valid,
    )


def test_rule1_previous_none_returns_missing_index() -> None:
    assert classify_sql_gap(None, _m()) is SQLGapClass.MISSING_INDEX


def test_rule2_invalid_current_returns_missing_index() -> None:
    assert classify_sql_gap(_m(), _m(is_valid=False)) is SQLGapClass.MISSING_INDEX


def test_rule3_strictly_better_returns_no_gap_sentinel() -> None:
    assert classify_sql_gap(_m(rows_examined=1000), _m(rows_examined=500)) == NO_GAP


def test_rule4_both_axes_worse_returns_cost_regression() -> None:
    assert classify_sql_gap(_m(rows_examined=100, rows_returned=10), _m(rows_examined=200, rows_returned=20)) is SQLGapClass.COST_REGRESSION


def test_rule5_rows_examined_better_rows_returned_much_worse_returns_inefficient_aggregate() -> None:
    # rows_returned goes 10 -> 30 (3x > 2x threshold).
    assert classify_sql_gap(_m(rows_examined=1000, rows_returned=10), _m(rows_examined=500, rows_returned=30)) is SQLGapClass.INEFFICIENT_AGGREGATE


def test_rule5b_rows_examined_better_rows_returned_tolerable_returns_missing_index() -> None:
    # rows_returned 10 -> 15 (1.5x < 2x threshold — tolerable).
    assert classify_sql_gap(_m(rows_examined=1000, rows_returned=10), _m(rows_examined=500, rows_returned=15)) is SQLGapClass.MISSING_INDEX





def test_rule6_rows_examined_worse_rows_returned_better_returns_wrong_join_order() -> None:
    assert classify_sql_gap(_m(rows_examined=100, rows_returned=10), _m(rows_examined=200, rows_returned=5)) is SQLGapClass.WRONG_JOIN_ORDER


def test_no_gap_sentinel_is_string_not_enum_value() -> None:
    assert isinstance(NO_GAP, str)
    assert not isinstance(NO_GAP, SQLGapClass)


def test_is_sql_improved_delegates_to_metrics_better_than() -> None:
    assert is_sql_improved(_m(rows_examined=1000), _m(rows_examined=500))
    assert not is_sql_improved(_m(rows_examined=500), _m(rows_examined=1000))


def test_pure_function_repeated_calls_return_same_value() -> None:
    a = classify_sql_gap(_m(), _m(rows_examined=500))
    b = classify_sql_gap(_m(), _m(rows_examined=500))
    assert a == b


def test_module_infra_free() -> None:
    mod = importlib.import_module("active_skill_system.application.use_cases.sql_gap_detector")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"sql_gap_detector.py must not contain '{forbidden}' (R002)"
