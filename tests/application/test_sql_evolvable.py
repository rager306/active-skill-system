"""Tests for SQLEvolvable (M018 S03)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from active_skill_system.application.evolvable_adapters import SQLEvolvable
from active_skill_system.domain.evolvable import Evolvable, FitnessSignal, MutationSpace
from active_skill_system.domain.sql_types import (
    SQLMetrics,
    SQLNodeKind,
    SQLTransformParams,
)


def _baseline_dict(rows: int = 1000) -> dict:
    return {"rows_examined": rows, "rows_returned": 10, "time_ms": 100.0, "plan_cost": 50.0, "is_valid": True}


def _add_index(cols: int = 5) -> SQLTransformParams:
    return SQLTransformParams(transform_type=SQLNodeKind.SQL_TRANSFORM_ADD_INDEX, params={"cols": cols}, legal=True)


def _reorder(order_size: int = 2) -> SQLTransformParams:
    return SQLTransformParams(transform_type=SQLNodeKind.SQL_TRANSFORM_REORDER_JOINS, params={"order_size": order_size}, legal=True)


def _rewrite_as_join(tables: int = 2) -> SQLTransformParams:
    return SQLTransformParams(transform_type=SQLNodeKind.SQL_TRANSFORM_REWRITE_AS_JOIN, params={"tables": tables}, legal=True)


def _improving_invoker(baseline_rows: int = 1000) -> object:
    def _invoke(args: dict) -> tuple[bool, str]:
        # Reduce rows_examined by half (deterministic improvement).
        m = SQLMetrics(rows_examined=max(1, baseline_rows // 2), rows_returned=10, time_ms=100.0, plan_cost=50.0, is_valid=True)
        return (True, json.dumps({
            "rows_examined": m.rows_examined, "rows_returned": m.rows_returned,
            "time_ms": m.time_ms, "plan_cost": m.plan_cost, "is_valid": m.is_valid,
        }))
    return _invoke


# ── Conformance ──────────────────────────────────────────────────────────


def test_sql_evolvable_is_evolvable() -> None:
    assert isinstance(SQLEvolvable(invoker=_improving_invoker()), Evolvable)


def test_mutation_space_mentions_three_strategies() -> None:
    ms = SQLEvolvable(invoker=_improving_invoker()).mutation_space
    assert isinstance(ms, MutationSpace)
    assert "ADD_INDEX" in ms.description
    assert "REORDER_JOINS" in ms.description
    assert "REWRITE_AS_JOIN" in ms.description


def test_init_rejects_missing_invoker() -> None:
    with pytest.raises((TypeError, ValueError)):
        SQLEvolvable()  # type: ignore[call-arg]


# ── Mutation strategies ──────────────────────────────────────────────────


def test_mutate_add_index_bumps_cols() -> None:
    e = SQLEvolvable(invoker=_improving_invoker())
    mutated = e.mutate((_add_index(cols=5),))
    assert mutated[0].params["cols"] == 6


def test_mutate_add_index_caps_at_16() -> None:
    e = SQLEvolvable(invoker=_improving_invoker())
    mutated = e.mutate((_add_index(cols=16),))
    assert mutated[0].params["cols"] == 16


def test_mutate_reorder_joins_bumps_order_size() -> None:
    e = SQLEvolvable(invoker=_improving_invoker())
    mutated = e.mutate((_reorder(order_size=2),))
    assert mutated[0].params["order_size"] == 3


def test_mutate_rewrite_as_join_bumps_tables() -> None:
    e = SQLEvolvable(invoker=_improving_invoker())
    mutated = e.mutate((_rewrite_as_join(tables=2),))
    assert mutated[0].params["tables"] == 3


def test_mutate_picks_first_applicable() -> None:
    e = SQLEvolvable(invoker=_improving_invoker())
    # First candidate (REWRITE_AS_JOIN) is bumped; second (ADD_INDEX) is unchanged.
    mutated = e.mutate((_rewrite_as_join(tables=2), _add_index(cols=5)))
    assert mutated[0].params["tables"] == 3  # bumped
    assert mutated[1].params == {"cols": 5}  # unchanged


def test_mutate_empty_genome_returns_empty() -> None:
    e = SQLEvolvable(invoker=_improving_invoker())
    assert e.mutate(()) == ()


# ── Type safety ──────────────────────────────────────────────────────────


def test_mutate_rejects_non_tuple() -> None:
    e = SQLEvolvable(invoker=_improving_invoker())
    with pytest.raises(TypeError):
        e.mutate([_add_index()])  # list, not tuple


def test_mutate_rejects_non_sql_transform_params() -> None:
    e = SQLEvolvable(invoker=_improving_invoker())
    with pytest.raises(TypeError):
        e.mutate(({"not": "a transform"},))


# ── Evaluate ─────────────────────────────────────────────────────────────


def test_evaluate_returns_fitness_signal() -> None:
    e = SQLEvolvable(invoker=_improving_invoker(baseline_rows=1000))
    result = e.evaluate((_add_index(),), {"baseline_metrics": _baseline_dict()})
    assert isinstance(result, FitnessSignal)
    assert result.regression is False
    # 1000 -> 500 = 50% reduction ratio.
    assert result.quality == pytest.approx(0.5)


def test_evaluate_regression_true_when_no_candidate_improves() -> None:
    def _invoke(args: dict) -> tuple[bool, str]:
        worse = SQLMetrics(rows_examined=9999, rows_returned=999, time_ms=999.0, plan_cost=999.0, is_valid=True)
        return (True, json.dumps({
            "rows_examined": worse.rows_examined, "rows_returned": worse.rows_returned,
            "time_ms": worse.time_ms, "plan_cost": worse.plan_cost, "is_valid": worse.is_valid,
        }))
    e = SQLEvolvable(invoker=_invoke)
    result = e.evaluate((_add_index(),), {"baseline_metrics": _baseline_dict()})
    assert result.regression is True
    assert result.quality == 0.0


def test_evaluate_skips_tool_failures() -> None:
    e = SQLEvolvable(invoker=lambda args: (False, ""))
    result = e.evaluate((_add_index(),), {"baseline_metrics": _baseline_dict()})
    assert result.regression is True


def test_evaluate_respects_max_candidates() -> None:
    call_count = 0

    def _invoke(args: dict) -> tuple[bool, str]:
        nonlocal call_count
        call_count += 1
        m = SQLMetrics(rows_examined=500, rows_returned=10, time_ms=100.0, plan_cost=50.0, is_valid=True)
        return (True, json.dumps({
            "rows_examined": m.rows_examined, "rows_returned": m.rows_returned,
            "time_ms": m.time_ms, "plan_cost": m.plan_cost, "is_valid": m.is_valid,
        }))
    e = SQLEvolvable(invoker=_invoke)
    e.evaluate((_add_index(), _reorder(), _rewrite_as_join()), {"baseline_metrics": _baseline_dict(), "max_candidates": 1})
    assert call_count == 1


# ── R002 ────────────────────────────────────────────────────────────────


def test_evolvable_adapters_module_keeps_r002_for_sql_extensions() -> None:
    """Module-level import of new SQL types in evolvable_adapters.py must not break R002.

    The module already had `import activegraph`/`from activegraph` etc. forbidden
    by import-linter; this test asserts the same property for the new SQLEvolvable section.
    """
    from active_skill_system.application import evolvable_adapters
    src = Path(evolvable_adapters.__file__).read_text(encoding="utf-8")
    assert "import activegraph" not in src
    assert "from activegraph" not in src
    assert "import anthropic" not in src
    assert "import openai" not in src
