"""L2 Application — IaC optimization loop (M023 S03)."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from active_skill_system.application.tools.registry import ToolRegistry
from active_skill_system.application.use_cases.iac_gap_detector import (
    NO_GAP,
    classify_iac_gap,
    is_iac_improved,
)
from active_skill_system.application.use_cases.iac_repair_policy import IaCRepairPolicy
from active_skill_system.domain.iac_types import (
    IaCActionType,
    IaCGapClass,
    IaCPlanMetrics,
    IaCTransformParams,
)


class IaCLoopStatus(StrEnum):
    COMPLETED = "completed"
    NO_IMPROVEMENT = "no_improvement"
    PARTIAL = "partial"
    FAILED = "failed"
    REPLAN_REQUIRED = "replan_required"


@dataclass(frozen=True)
class IaCLoopTraceStep:
    iteration: int
    gap: IaCGapClass | str
    action: IaCActionType
    accepted: bool


@dataclass(frozen=True)
class IaCLoopResult:
    final_metrics: IaCPlanMetrics
    iterations_used: int
    candidates_tried: int
    accepted_count: int
    status: IaCLoopStatus
    trace: tuple[IaCLoopTraceStep, ...]


def _parse_metrics(payload: str) -> IaCPlanMetrics | None:
    try:
        d = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    try:
        return IaCPlanMetrics(
            resource_count=int(d["resource_count"]),
            module_count=int(d["module_count"]),
            variable_count=int(d["variable_count"]),
            drift_score=float(d["drift_score"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except (KeyError, TypeError, ValueError):
        return None


class IaCOptimizationLoopUseCase:
    """Bounded IaC plan optimization driver."""

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        policy: IaCRepairPolicy | None = None,
        gap_detector: Callable[..., Any] | None = None,
        max_cycles: int = 10,
    ) -> None:
        self._registry = tool_registry if tool_registry is not None else ToolRegistry()
        self._policy = policy if policy is not None else IaCRepairPolicy.default_policy()
        self._gap_detector = gap_detector if gap_detector is not None else classify_iac_gap
        self._max_cycles = max(1, max_cycles)

    def run(
        self,
        baseline: IaCPlanMetrics,
        candidates: tuple[IaCTransformParams, ...],
    ) -> IaCLoopResult:
        if not candidates:
            return IaCLoopResult(
                final_metrics=baseline, iterations_used=0, candidates_tried=0,
                accepted_count=0, status=IaCLoopStatus.NO_IMPROVEMENT, trace=(),
            )
        tool = self._registry.get_by_capability("compute")
        if tool is None:
            return IaCLoopResult(
                final_metrics=baseline, iterations_used=0, candidates_tried=0,
                accepted_count=0, status=IaCLoopStatus.FAILED, trace=(),
            )
        current = baseline
        accepted_count = 0
        iterations_used = 0
        trace: list[IaCLoopTraceStep] = []
        for i in range(self._max_cycles):
            if i >= len(candidates):
                break
            cand = candidates[i]
            iterations_used += 1
            gap = self._gap_detector(baseline, current)
            if gap == NO_GAP:
                trace.append(IaCLoopTraceStep(
                    iteration=iterations_used, gap=gap,
                    action=IaCActionType.REPLAN_PROVIDERS, accepted=True,
                ))
                return IaCLoopResult(
                    final_metrics=current, iterations_used=iterations_used,
                    candidates_tried=i + 1, accepted_count=accepted_count + 1,
                    status=IaCLoopStatus.COMPLETED, trace=tuple(trace),
                )
            assert isinstance(gap, IaCGapClass)
            action = self._policy.action_for(gap)
            if action is IaCActionType.REPLAN_PROVIDERS:
                return IaCLoopResult(
                    final_metrics=current, iterations_used=iterations_used,
                    candidates_tried=i + 1, accepted_count=accepted_count,
                    status=IaCLoopStatus.REPLAN_REQUIRED, trace=tuple(trace),
                )
            args = {
                "transform_type": cand.transform_type.value,
                "params": {**cand.params, "legal": cand.legal},
                "baseline": {
                    "resource_count": current.resource_count,
                    "module_count": current.module_count,
                    "variable_count": current.variable_count,
                    "drift_score": current.drift_score,
                    "is_valid": current.is_valid,
                },
            }
            result = tool.invoke(args)
            if not result.success:
                continue
            new_metrics = _parse_metrics(result.text)
            if new_metrics is None:
                continue
            gap = self._gap_detector(current, new_metrics)
            accepted = is_iac_improved(current, new_metrics)
            trace.append(IaCLoopTraceStep(
                iteration=iterations_used, gap=gap, action=action, accepted=accepted,
            ))
            if accepted:
                current = new_metrics
                accepted_count += 1
                return IaCLoopResult(
                    final_metrics=current, iterations_used=iterations_used,
                    candidates_tried=i + 1, accepted_count=accepted_count,
                    status=IaCLoopStatus.COMPLETED, trace=tuple(trace),
                )
        return IaCLoopResult(
            final_metrics=current, iterations_used=iterations_used,
            candidates_tried=iterations_used, accepted_count=accepted_count,
            status=IaCLoopStatus.NO_IMPROVEMENT, trace=tuple(trace),
        )