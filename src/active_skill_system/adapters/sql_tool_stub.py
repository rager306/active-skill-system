"""L3 Adapter — SQLToolStub (M018 S02).

Deterministic stub tool that simulates applying a SQL plan transform to
a baseline ``SQLMetrics`` and returns the resulting metrics. Used by the
SQL plan optimization loop (S03) to evaluate candidate transforms without
invoking a real database. Deterministic, infra-free, registered under
``ToolCapability.COMPUTE``.

Formulae (chosen so every transform has an observable, monotone effect on
the primary axis ``rows_examined``, matching typical query-optimizer
behavior):

  ADD_INDEX(cols=N)        : rows_examined //= max(1, N), plan_cost += N*5
  REORDER_JOINS(order_size=K): rows_examined //= max(1, K), time_ms *= 0.85
  REWRITE_AS_JOIN(tables=N): rows_examined //= max(1, N), time_ms -= 5.0
  REPLAN_QUERY             : rows_examined unchanged, plan_cost //= 2, time_ms -= 10.0

A missing transform_type returns the baseline unchanged (the
``MISSING_INDEX`` gap case). An illegal transform (``legal=False``) or
an unknown ``SQL_TRANSFORM_*`` kind raises ``ValueError``, which the
SQL loop catches and surfaces as a ``COST_REGRESSION`` gap. Metrics are
clamped to >= 0 to keep ``SQLMetrics`` invariants.

Mirrors ``adapters/compiler_tool_stub.py`` (M016 S02) but on SQL
primitives — same ToolCapability.COMPUTE registration, same failure
shape (ToolResult(success=False), no exceptions per D007).
"""

from __future__ import annotations

import json
from typing import Any

from active_skill_system.application.ports.tool import (
    ToolCapability,
    ToolProfile,
    ToolResult,
)
from active_skill_system.domain.sql_types import SQLMetrics, SQLNodeKind


def _metrics_from_dict(d: dict[str, Any]) -> SQLMetrics:
    if not isinstance(d, dict):
        raise ValueError(f"baseline must be a dict (got {type(d).__name__})")
    try:
        return SQLMetrics(
            rows_examined=int(d["rows_examined"]),
            rows_returned=int(d["rows_returned"]),
            time_ms=float(d["time_ms"]),
            plan_cost=float(d["plan_cost"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except KeyError as e:
        raise ValueError(f"baseline missing required key: {e.args[0]!r}") from None
    except (TypeError, ValueError) as e:
        raise ValueError(f"baseline has invalid values: {e}") from None


def _apply_transform(
    kind: SQLNodeKind,
    params: dict[str, Any],
    baseline: SQLMetrics,
) -> SQLMetrics:
    rows_examined = baseline.rows_examined
    rows_returned = baseline.rows_returned
    time_ms = float(baseline.time_ms)
    plan_cost = float(baseline.plan_cost)

    if kind is SQLNodeKind.SQL_TRANSFORM_ADD_INDEX:
        n = int(params.get("cols", 1))
        if n < 1:
            raise ValueError(f"cols must be >= 1 (got {n!r})")
        rows_examined = max(1, rows_examined // n)
        plan_cost = plan_cost + 5 * n
    elif kind is SQLNodeKind.SQL_TRANSFORM_REORDER_JOINS:
        k = int(params.get("order_size", 2))
        if k < 1:
            raise ValueError(f"order_size must be >= 1 (got {k!r})")
        rows_examined = max(1, rows_examined // k)
        time_ms = time_ms * 0.85
    elif kind is SQLNodeKind.SQL_TRANSFORM_REWRITE_AS_JOIN:
        n = int(params.get("tables", 2))
        if n < 1:
            raise ValueError(f"tables must be >= 1 (got {n!r})")
        rows_examined = max(1, rows_examined // n)
        time_ms = max(0.0, time_ms - 5.0)
    elif kind is SQLNodeKind.SQL_TRANSFORM_REPLAN_QUERY:
        # plan_cost halves, time_ms drops by 10ms, rows_examined unchanged.
        plan_cost = max(0.0, plan_cost / 2.0)
        time_ms = max(0.0, time_ms - 10.0)
    else:
        raise ValueError(f"unsupported SQL transform kind: {kind!r}")

    return SQLMetrics(
        rows_examined=rows_examined,
        rows_returned=rows_returned,
        time_ms=time_ms,
        plan_cost=plan_cost,
        is_valid=True,
    )


class SQLToolStub:
    """Deterministic tool that simulates applying a SQL plan transform.

    capabilities: {compute}
    profile: NORMAL (deterministic, no side effects)
    invoke({"transform_type": "sql_transform_add_index", "params": {...}, "baseline": {...}})
        → ToolResult(text=json.dumps(metrics), success=True)
    """

    name = "sql_apply_transform"
    capabilities = frozenset({ToolCapability.COMPUTE})
    profile = ToolProfile.NORMAL

    def invoke(self, args: dict[str, Any]) -> ToolResult:
        if not isinstance(args, dict):
            return ToolResult(text="", evidence_id=None, success=False)

        kind_raw = args.get("transform_type")
        params_raw = args.get("params", {})
        baseline_raw = args.get("baseline")

        if kind_raw is None:
            # MISSING_INDEX gap case: return baseline unchanged.
            try:
                baseline = _metrics_from_dict(baseline_raw if isinstance(baseline_raw, dict) else {})
            except ValueError:
                return ToolResult(text="", evidence_id=None, success=False)
            return ToolResult(
                text=json.dumps(_metrics_to_dict(baseline), sort_keys=True),
                evidence_id="missing_transform",
                success=True,
            )

        try:
            kind = SQLNodeKind(kind_raw) if not isinstance(kind_raw, SQLNodeKind) else kind_raw
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)

        try:
            baseline = _metrics_from_dict(baseline_raw if isinstance(baseline_raw, dict) else {})
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)

        if not isinstance(params_raw, dict):
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)

        if params_raw.get("legal", True) is False:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)

        try:
            new_metrics = _apply_transform(kind, params_raw, baseline)
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)

        return ToolResult(
            text=json.dumps(_metrics_to_dict(new_metrics), sort_keys=True),
            evidence_id=str(kind_raw),
            success=True,
        )


def _metrics_to_dict(m: SQLMetrics) -> dict[str, Any]:
    return {
        "rows_examined": m.rows_examined,
        "rows_returned": m.rows_returned,
        "time_ms": m.time_ms,
        "plan_cost": m.plan_cost,
        "is_valid": m.is_valid,
    }
