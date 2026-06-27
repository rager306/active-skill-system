"""Tests for domain/sql_types.py (M018 S01)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from active_skill_system.domain.sql_types import (
    SQLActionType,
    SQLGapClass,
    SQLMetrics,
    SQLNodeKind,
    SQLTransformParams,
)

# ── SQLNodeKind ────────────────────────────────────────────────────────────


def test_sql_node_kind_has_plan_kinds() -> None:
    assert SQLNodeKind.TABLE_SCAN.value == "table_scan"
    assert SQLNodeKind.INDEX_SCAN.value == "index_scan"
    assert SQLNodeKind.NESTED_LOOP.value == "nested_loop"
    assert SQLNodeKind.HASH_JOIN.value == "hash_join"
    assert SQLNodeKind.FILTER.value == "filter"
    assert SQLNodeKind.SORT.value == "sort"
    assert SQLNodeKind.AGGREGATE.value == "aggregate"


def test_sql_node_kind_has_transform_kinds() -> None:
    assert SQLNodeKind.SQL_TRANSFORM_ADD_INDEX.value == "sql_transform_add_index"
    assert SQLNodeKind.SQL_TRANSFORM_REORDER_JOINS.value == "sql_transform_reorder_joins"
    assert SQLNodeKind.SQL_TRANSFORM_REWRITE_AS_JOIN.value == "sql_transform_rewrite_as_join"
    assert SQLNodeKind.SQL_TRANSFORM_REPLAN_QUERY.value == "sql_transform_replan_query"


# ── SQLGapClass ────────────────────────────────────────────────────────────


def test_sql_gap_class_has_five_values() -> None:
    assert len(SQLGapClass) == 5
    assert SQLGapClass.MISSING_INDEX.value == "missing_index"
    assert SQLGapClass.FULL_TABLE_SCAN.value == "full_table_scan"
    assert SQLGapClass.WRONG_JOIN_ORDER.value == "wrong_join_order"
    assert SQLGapClass.INEFFICIENT_AGGREGATE.value == "inefficient_aggregate"
    assert SQLGapClass.COST_REGRESSION.value == "cost_regression"


# ── SQLActionType ──────────────────────────────────────────────────────────


def test_sql_action_type_has_four_values() -> None:
    assert len(SQLActionType) == 4
    assert SQLActionType.ADD_INDEX.value == "add_index"
    assert SQLActionType.REORDER_JOINS.value == "reorder_joins"
    assert SQLActionType.REWRITE_AS_JOIN.value == "rewrite_as_join"
    assert SQLActionType.REPLAN_QUERY.value == "replan_query"


# ── SQLTransformParams ─────────────────────────────────────────────────────


def test_sql_transform_params_accepts_valid_kind() -> None:
    p = SQLTransformParams(
        transform_type=SQLNodeKind.SQL_TRANSFORM_ADD_INDEX,
        params={"index_col": "user_id"},
        legal=True,
    )
    assert p.transform_type is SQLNodeKind.SQL_TRANSFORM_ADD_INDEX
    assert p.params["index_col"] == "user_id"


def test_sql_transform_params_rejects_non_transform_kind() -> None:
    with pytest.raises(ValueError, match="SQL_TRANSFORM"):
        SQLTransformParams(
            transform_type=SQLNodeKind.TABLE_SCAN,
            params={},
            legal=True,
        )


def test_sql_transform_params_rejects_non_dict_params() -> None:
    with pytest.raises(ValueError, match="params must be a dict"):
        SQLTransformParams(
            transform_type=SQLNodeKind.SQL_TRANSFORM_ADD_INDEX,
            params=["not", "a", "dict"],  # type: ignore[arg-type]
            legal=True,
        )


def test_sql_transform_params_rejects_non_bool_legal() -> None:
    with pytest.raises(ValueError, match="legal must be a bool"):
        SQLTransformParams(
            transform_type=SQLNodeKind.SQL_TRANSFORM_ADD_INDEX,
            params={},
            legal="yes",  # type: ignore[arg-type]
        )


# ── SQLMetrics ─────────────────────────────────────────────────────────────


def _baseline_metrics(rows_examined: int = 1000) -> SQLMetrics:
    return SQLMetrics(
        rows_examined=rows_examined,
        rows_returned=10,
        time_ms=100.0,
        plan_cost=50.0,
        is_valid=True,
    )


def test_sql_metrics_rejects_negative_rows_examined() -> None:
    with pytest.raises(ValueError, match="rows_examined"):
        SQLMetrics(rows_examined=-1, rows_returned=0, time_ms=0.0, plan_cost=0.0)


def test_sql_metrics_rejects_negative_time() -> None:
    with pytest.raises(ValueError, match="time_ms"):
        SQLMetrics(rows_examined=0, rows_returned=0, time_ms=-1.0, plan_cost=0.0)


def test_sql_metrics_rejects_non_bool_is_valid() -> None:
    with pytest.raises(ValueError, match="is_valid"):
        SQLMetrics(rows_examined=0, rows_returned=0, time_ms=0.0, plan_cost=0.0, is_valid=1)  # type: ignore[arg-type]


def test_sql_metrics_better_than_strictly_lower_rows_examined() -> None:
    base = _baseline_metrics(rows_examined=1000)
    better = _baseline_metrics(rows_examined=500)
    assert better.better_than(base)
    assert not base.better_than(better)


def test_sql_metrics_better_than_tie_break_by_rows_returned() -> None:
    base = SQLMetrics(rows_examined=1000, rows_returned=100, time_ms=100.0, plan_cost=50.0, is_valid=True)
    better = SQLMetrics(rows_examined=1000, rows_returned=50, time_ms=100.0, plan_cost=50.0, is_valid=True)
    assert better.better_than(base)


def test_sql_metrics_better_than_tie_break_by_time_ms() -> None:
    base = SQLMetrics(rows_examined=1000, rows_returned=100, time_ms=100.0, plan_cost=50.0, is_valid=True)
    better = SQLMetrics(rows_examined=1000, rows_returned=100, time_ms=50.0, plan_cost=50.0, is_valid=True)
    assert better.better_than(base)


def test_sql_metrics_invalid_never_beats_valid() -> None:
    valid = _baseline_metrics(rows_examined=10000)
    invalid = SQLMetrics(rows_examined=1, rows_returned=1, time_ms=1.0, plan_cost=1.0, is_valid=False)
    assert not invalid.better_than(valid)
    assert valid.better_than(invalid)


def test_sql_metrics_plan_cost_does_not_affect_ranking() -> None:
    """plan_cost is reported but not in the ranking (mirrors reg_pressure in M016)."""
    base = SQLMetrics(rows_examined=1000, rows_returned=100, time_ms=100.0, plan_cost=50.0, is_valid=True)
    worse_cost_better_other = SQLMetrics(rows_examined=1000, rows_returned=100, time_ms=100.0, plan_cost=999.0, is_valid=True)
    assert not worse_cost_better_other.better_than(base)
    assert not base.better_than(worse_cost_better_other)


def test_sql_metrics_better_than_handles_invalid_inputs() -> None:
    """Passing a non-SQLMetrics to better_than returns False (defensive)."""
    m = _baseline_metrics()
    assert not m.better_than("not metrics")  # type: ignore[arg-type]


# ── R002 ──────────────────────────────────────────────────────────────────


def test_sql_types_module_infra_free() -> None:
    """The sql_types module must not import activegraph / anthropic / openai."""
    mod = importlib.import_module("active_skill_system.domain.sql_types")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "import activegraph",
        "from activegraph",
        "import anthropic",
        "import openai",
    ):
        assert forbidden not in src, (
            f"sql_types.py must not contain '{forbidden}' (R002 - domain is infra-free)"
        )


def test_sql_metrics_is_frozen() -> None:
    """frozen dataclass invariant (matches M016 S01 pattern)."""
    m = _baseline_metrics()
    with pytest.raises(Exception):  # FrozenInstanceError
        m.rows_examined = 999  # type: ignore[misc]
