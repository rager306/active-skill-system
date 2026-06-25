"""Unit tests for SQLToolStub (M018 S02)."""

from __future__ import annotations

import json
from pathlib import Path

from active_skill_system.adapters.sql_tool_stub import SQLToolStub
from active_skill_system.application.ports.tool import ToolCapability, ToolProfile, ToolResult
from active_skill_system.domain.sql_types import SQLMetrics


def _baseline_metrics(rows_examined: int = 1000) -> SQLMetrics:
    return SQLMetrics(
        rows_examined=rows_examined,
        rows_returned=10,
        time_ms=100.0,
        plan_cost=50.0,
        is_valid=True,
    )


def _baseline_dict(rows_examined: int = 1000) -> dict:
    m = _baseline_metrics(rows_examined)
    return {
        "rows_examined": m.rows_examined,
        "rows_returned": m.rows_returned,
        "time_ms": m.time_ms,
        "plan_cost": m.plan_cost,
        "is_valid": m.is_valid,
    }


# ── Tool surface ──────────────────────────────────────────────────────────


def test_tool_name_and_capabilities() -> None:
    tool = SQLToolStub()
    assert tool.name == "sql_apply_transform"
    assert ToolCapability.COMPUTE in tool.capabilities
    assert tool.profile == ToolProfile.NORMAL


# ── Transform formulas ────────────────────────────────────────────────────


def test_add_index_divides_rows_examined_by_cols() -> None:
    """ADD_INDEX(cols=N): rows_examined //= max(1, N), plan_cost += N*5."""
    tool = SQLToolStub()
    result = tool.invoke({
        "transform_type": "sql_transform_add_index",
        "params": {"cols": 10},
        "baseline": _baseline_dict(rows_examined=1000),
    })
    assert result.success is True
    assert result.evidence_id == "sql_transform_add_index"
    parsed = json.loads(result.text)
    assert parsed["rows_examined"] == 100  # 1000 // 10
    assert parsed["plan_cost"] == 50.0 + 5 * 10  # 100.0


def test_reorder_joins_divides_rows_examined_and_drops_time() -> None:
    """REORDER_JOINS(order_size=K): rows_examined //= max(1, K), time_ms *= 0.85."""
    tool = SQLToolStub()
    result = tool.invoke({
        "transform_type": "sql_transform_reorder_joins",
        "params": {"order_size": 4},
        "baseline": _baseline_dict(rows_examined=1000),
    })
    assert result.success is True
    parsed = json.loads(result.text)
    assert parsed["rows_examined"] == 250  # 1000 // 4
    assert abs(parsed["time_ms"] - 85.0) < 1e-9  # 100 * 0.85


def test_rewrite_as_join_divides_rows_examined_and_subtracts_time() -> None:
    """REWRITE_AS_JOIN(tables=N): rows_examined //= max(1, N), time_ms -= 5.0."""
    tool = SQLToolStub()
    result = tool.invoke({
        "transform_type": "sql_transform_rewrite_as_join",
        "params": {"tables": 2},
        "baseline": _baseline_dict(rows_examined=1000),
    })
    assert result.success is True
    parsed = json.loads(result.text)
    assert parsed["rows_examined"] == 500
    assert parsed["time_ms"] == 95.0  # 100 - 5


def test_replan_query_keeps_rows_examined_halves_cost_drops_time() -> None:
    """REPLAN_QUERY: rows_examined unchanged, plan_cost //= 2, time_ms -= 10.0."""
    tool = SQLToolStub()
    result = tool.invoke({
        "transform_type": "sql_transform_replan_query",
        "params": {},
        "baseline": _baseline_dict(rows_examined=1000),
    })
    assert result.success is True
    parsed = json.loads(result.text)
    assert parsed["rows_examined"] == 1000
    assert parsed["plan_cost"] == 25.0  # 50 / 2
    assert parsed["time_ms"] == 90.0  # 100 - 10


# ── Failure modes (D007 uniform shape: ToolResult(success=False), no exceptions) ──


def test_missing_transform_type_returns_baseline() -> None:
    """Missing transform_type returns the baseline unchanged (MISSING_INDEX gap case)."""
    tool = SQLToolStub()
    result = tool.invoke({"baseline": _baseline_dict()})
    assert result.success is True
    assert result.evidence_id == "missing_transform"
    parsed = json.loads(result.text)
    assert parsed["rows_examined"] == 1000


def test_unknown_transform_kind_returns_failure() -> None:
    """Unknown SQL_TRANSFORM_* kind returns ToolResult(success=False), no exception."""
    tool = SQLToolStub()
    result = tool.invoke({
        "transform_type": "sql_transform_bogus",
        "params": {},
        "baseline": _baseline_dict(),
    })
    assert result.success is False


def test_illegal_transform_returns_failure() -> None:
    """legal=False transform returns ToolResult(success=False)."""
    tool = SQLToolStub()
    result = tool.invoke({
        "transform_type": "sql_transform_add_index",
        "params": {"cols": 2, "legal": False},
        "baseline": _baseline_dict(),
    })
    assert result.success is False


def test_non_dict_args_returns_failure() -> None:
    tool = SQLToolStub()
    result = tool.invoke("not a dict")  # type: ignore[arg-type]
    assert isinstance(result, ToolResult)
    assert result.success is False


def test_baseline_missing_required_key_returns_failure() -> None:
    tool = SQLToolStub()
    result = tool.invoke({
        "transform_type": "sql_transform_add_index",
        "params": {"cols": 2},
        "baseline": {"rows_examined": 100},  # missing rows_returned, time_ms, plan_cost
    })
    assert result.success is False


def test_invalid_param_returns_failure() -> None:
    """cols=0 raises ValueError, surfaced as ToolResult(success=False)."""
    tool = SQLToolStub()
    result = tool.invoke({
        "transform_type": "sql_transform_add_index",
        "params": {"cols": 0},
        "baseline": _baseline_dict(),
    })
    assert result.success is False


# ── Module hygiene (R002) ──────────────────────────────────────────────────


def test_module_infra_free() -> None:
    """sql_tool_stub.py must not import activegraph / anthropic / openai (R002 — adapters can import L3 but not L0 infra).

    Adapters live at L3 and CAN import infra ports; the check is that the adapter
    itself does not pull in domain-incompatible primitives beyond its ports.
    The adapter imports only application.ports.tool (its own port) + the domain
    SQLMetrics type.
    """
    from active_skill_system.adapters import sql_tool_stub
    src = Path(sql_tool_stub.__file__).read_text(encoding="utf-8")
    # Adapters may import from activegraph (L3 boundary), but this stub does not — it's pure deterministic.
    assert "activegraph" not in src
    assert "anthropic" not in src
    assert "openai" not in src
