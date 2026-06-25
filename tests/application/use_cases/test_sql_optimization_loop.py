"""Tests for SQLOptimizationLoopUseCase (M018 S03)."""

from __future__ import annotations

import importlib
from pathlib import Path

from active_skill_system.adapters.sql_tool_stub import SQLToolStub
from active_skill_system.application.tools.registry import ToolRegistry
from active_skill_system.application.use_cases.sql_optimization_loop import (
    SQLOopStatus,
    SQLOptimizationLoopUseCase,
)
from active_skill_system.domain.sql_types import SQLMetrics, SQLNodeKind, SQLTransformParams


def _baseline(rows: int = 1000) -> SQLMetrics:
    return SQLMetrics(rows_examined=rows, rows_returned=10, time_ms=100.0, plan_cost=50.0, is_valid=True)


def _add_index(cols: int = 5) -> SQLTransformParams:
    return SQLTransformParams(transform_type=SQLNodeKind.SQL_TRANSFORM_ADD_INDEX, params={"cols": cols}, legal=True)


def _reorder(order_size: int = 2) -> SQLTransformParams:
    return SQLTransformParams(transform_type=SQLNodeKind.SQL_TRANSFORM_REORDER_JOINS, params={"order_size": order_size}, legal=True)


def _rewrite_as_join(tables: int = 2) -> SQLTransformParams:
    return SQLTransformParams(transform_type=SQLNodeKind.SQL_TRANSFORM_REWRITE_AS_JOIN, params={"tables": tables}, legal=True)


def test_completes_when_candidate_improves() -> None:
    """SQL loop: ADD_INDEX cols=10 reduces rows_examined 1000 -> 100 (10x speedup)."""
    registry = ToolRegistry()
    registry.register(SQLToolStub())
    loop = SQLOptimizationLoopUseCase(tool_registry=registry, max_cycles=3)
    result = loop.run(_baseline(rows=1000), (_add_index(cols=10),))
    assert result.status is SQLOopStatus.COMPLETED
    assert result.accepted_count == 1
    assert result.final_metrics.rows_examined < 1000


def test_no_improvement_when_candidates_exhausted() -> None:
    """Tiny baseline (rows=1) where ADD_INDEX cols=1 already gives max reduction — no further improvement."""
    registry = ToolRegistry()
    registry.register(SQLToolStub())
    loop = SQLOptimizationLoopUseCase(tool_registry=registry, max_cycles=3)
    # baseline rows=1, cols=1 -> rows //= 1 = 1 (no improvement), then cols bump but already at max
    result = loop.run(_baseline(rows=1), (_add_index(cols=1),))
    assert result.status in (SQLOopStatus.NO_IMPROVEMENT, SQLOopStatus.COMPLETED)


def test_loop_uses_registry_not_hardcoded_tool() -> None:
    registry = ToolRegistry()  # empty
    loop = SQLOptimizationLoopUseCase(tool_registry=registry, max_cycles=2)
    result = loop.run(_baseline(), (_add_index(),))
    assert result.status is SQLOopStatus.FAILED  # no tool registered


def test_default_policy_and_registry_used_when_not_provided() -> None:
    """Constructor without policy/registry uses sensible defaults."""
    loop = SQLOptimizationLoopUseCase(max_cycles=1)
    assert loop._policy is not None
    assert loop._registry is not None
    loop._registry.register(SQLToolStub())
    result = loop.run(_baseline(rows=1000), (_add_index(cols=10),))
    assert result.accepted_count == 1


def test_max_cycles_clamped_to_at_least_one() -> None:
    registry = ToolRegistry()
    registry.register(SQLToolStub())
    loop = SQLOptimizationLoopUseCase(tool_registry=registry, max_cycles=0)
    assert loop._max_cycles == 1


def test_module_infra_free() -> None:
    mod = importlib.import_module("active_skill_system.application.use_cases.sql_optimization_loop")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"sql_optimization_loop.py must not contain '{forbidden}' (R002)"
