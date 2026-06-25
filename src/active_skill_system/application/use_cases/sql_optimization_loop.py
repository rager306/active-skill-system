"""L2 Application — SQL optimization loop (M018 S03 T01).

Bounded loop driver mirroring ``compiler_optimization_loop.CompilationOptimizationLoopUseCase``
(M016 S03 T02) but on SQL primitives. Drives
``classify_sql_gap(previous -> new_metrics) -> SQLRepairPolicy.action_for -> SQLToolStub.invoke
-> measurable-improvement gate via SQLMetrics.better_than -> accept/reject``.

Terminal success on the FIRST accepted candidate (greedy). Returns
``SQLOopResult`` (frozen dataclass) with trace.

Pure application. NO infrastructure imports (R002).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from active_skill_system.application.tools.registry import ToolRegistry
from active_skill_system.application.use_cases.sql_gap_detector import (
    NO_GAP,
    classify_sql_gap,
    is_sql_improved,
)
from active_skill_system.application.use_cases.sql_repair_policy import SQLRepairPolicy
from active_skill_system.domain.sql_types import (
    SQLActionType,
    SQLGapClass,
    SQLMetrics,
    SQLTransformParams,
)


class SQLOopStatus(StrEnum):
    COMPLETED = "completed"
    NO_IMPROVEMENT = "no_improvement"
    PARTIAL = "partial"
    FAILED = "failed"
    REPLAN_REQUIRED = "replan_required"


@dataclass(frozen=True)
class SQLOopTraceStep:
    iteration: int
    gap: SQLGapClass | str  # SQLGapClass or NO_GAP sentinel
    action: SQLActionType
    accepted: bool


@dataclass(frozen=True)
class SQLOopResult:
    final_metrics: SQLMetrics
    iterations_used: int
    candidates_tried: int
    accepted_count: int
    status: SQLOopStatus
    trace: tuple[SQLOopTraceStep, ...]


def _parse_metrics(payload: str) -> SQLMetrics | None:
    try:
        d = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    try:
        return SQLMetrics(
            rows_examined=int(d["rows_examined"]),
            rows_returned=int(d["rows_returned"]),
            time_ms=float(d["time_ms"]),
            plan_cost=float(d["plan_cost"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except (KeyError, TypeError, ValueError):
        return None


class SQLOptimizationLoopUseCase:
    """Bounded SQL plan optimization driver.

    Mirrors CompilerOptimizationLoopUseCase (M016 S03 T02): each iteration
    picks candidates[i], invokes the SQL tool, classifies the gap, looks
    up the action, and accepts the candidate iff new_metrics is strictly
    better than current. Terminal on first accept.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        policy: SQLRepairPolicy | None = None,
        gap_detector: Callable[..., Any] | None = None,
        max_cycles: int = 10,
    ) -> None:
        self._registry = tool_registry if tool_registry is not None else ToolRegistry()
        self._policy = policy if policy is not None else SQLRepairPolicy.default_policy()
        self._gap_detector = gap_detector if gap_detector is not None else classify_sql_gap
        self._max_cycles = max(1, max_cycles)

    def run(
        self,
        baseline: SQLMetrics,
        candidates: tuple[SQLTransformParams, ...],
    ) -> SQLOopResult:
        if not candidates:
            return SQLOopResult(
                final_metrics=baseline,
                iterations_used=0,
                candidates_tried=0,
                accepted_count=0,
                status=SQLOopStatus.NO_IMPROVEMENT,
                trace=(),
            )

        tool = self._registry.get_by_capability("compute")
        if tool is None:
            # No tool registered -> cannot evaluate; return baseline unchanged.
            return SQLOopResult(
                final_metrics=baseline,
                iterations_used=0,
                candidates_tried=0,
                accepted_count=0,
                status=SQLOopStatus.FAILED,
                trace=(),
            )

        current = baseline
        accepted_count = 0
        iterations_used = 0
        trace: list[SQLOopTraceStep] = []

        for i in range(self._max_cycles):
            if i >= len(candidates):
                break
            cand = candidates[i]
            iterations_used += 1

            # First classify current vs baseline (no current result yet).
            gap = self._gap_detector(baseline, current)
            if gap == NO_GAP:
                trace.append(SQLOopTraceStep(
                    iteration=iterations_used, gap=gap, action=SQLActionType.REPLAN_QUERY, accepted=True,
                ))
                return SQLOopResult(
                    final_metrics=current,
                    iterations_used=iterations_used,
                    candidates_tried=i + 1,
                    accepted_count=accepted_count + 1,
                    status=SQLOopStatus.COMPLETED,
                    trace=tuple(trace),
                )

            assert isinstance(gap, SQLGapClass)
            action = self._policy.action_for(gap)

            if action is SQLActionType.REPLAN_QUERY:
                return SQLOopResult(
                    final_metrics=current,
                    iterations_used=iterations_used,
                    candidates_tried=i + 1,
                    accepted_count=accepted_count,
                    status=SQLOopStatus.REPLAN_REQUIRED,
                    trace=tuple(trace),
                )

            # Invoke the tool.
            args = {
                "transform_type": cand.transform_type.value,
                "params": {**cand.params, "legal": cand.legal},
                "baseline": {
                    "rows_examined": current.rows_examined,
                    "rows_returned": current.rows_returned,
                    "time_ms": current.time_ms,
                    "plan_cost": current.plan_cost,
                    "is_valid": current.is_valid,
                },
            }
            result = tool.invoke(args)
            if not result.success:
                continue
            new_metrics = _parse_metrics(result.text)
            if new_metrics is None:
                continue

            # Re-classify with the actual new metrics.
            gap = self._gap_detector(current, new_metrics)
            accepted = is_sql_improved(current, new_metrics)
            trace.append(SQLOopTraceStep(
                iteration=iterations_used, gap=gap, action=action, accepted=accepted,
            ))

            if accepted:
                current = new_metrics
                accepted_count += 1
                return SQLOopResult(
                    final_metrics=current,
                    iterations_used=iterations_used,
                    candidates_tried=i + 1,
                    accepted_count=accepted_count,
                    status=SQLOopStatus.COMPLETED,
                    trace=tuple(trace),
                )

        return SQLOopResult(
            final_metrics=current,
            iterations_used=iterations_used,
            candidates_tried=iterations_used,
            accepted_count=accepted_count,
            status=SQLOopStatus.NO_IMPROVEMENT,
            trace=tuple(trace),
        )
