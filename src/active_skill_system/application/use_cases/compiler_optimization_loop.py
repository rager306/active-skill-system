"""L2 Application use-case — CompilerOptimizationLoopUseCase (M016 S03 T02).

Bounded compiler optimization loop. Mirrors the pattern of
:class:`RepairLoopUseCase` (M009 S02) but for the compiler profile:

  classify (gap detector) → look up action (repair policy)
  → invoke tool via ToolRegistry → parse result → compare to current
  → accept (advance) OR reject (try next candidate) → loop until:
    * NO_GAP sentinel reached (success),
    * candidates exhausted,
    * LOWERING_REPLAN action reached (cannot recover), or
    * max_cycles reached.

The loop is purely a value-object driver: it depends only on a
:class:`ToolRegistry` (to look up the deterministic tool), a
:class:`CompilerRepairPolicy` (gap → action), and a gap-classifier
callable. Action execution and tool invocation are explicit parameters
so tests can inject fakes without touching the L3 adapter layer.

Pure application. Depends on application + domain only; no I/O (R002).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from active_skill_system.application.ports.tool import (
    ToolCapability,
    ToolPort,
)
from active_skill_system.application.tools.registry import ToolRegistry
from active_skill_system.application.use_cases.compiler_gap_detector import (
    classify_gap,
)
from active_skill_system.application.use_cases.compiler_repair_policy import (
    CompilerRepairPolicy,
)
from active_skill_system.domain.compiler_types import (
    CompilerActionType,
    CompilerGapClass,
    CompilerMetrics,
    TransformParams,
)


class LoopStatus(StrEnum):
    """Outcome of the compiler optimization loop."""

    COMPLETED = "completed"  # a candidate improved metrics (NO_GAP reached)
    NO_IMPROVEMENT = "no_improvement"  # all candidates tried, none beat baseline
    BUDGET_EXHAUSTED = "budget_exhausted"  # max_cycles hit before success
    REPLAN_REQUIRED = "replan_required"  # LOWERING_REPLAN action reached


@dataclass(frozen=True)
class CompilerLoopResult:
    """Result of the bounded compiler optimization loop.

    Carries:
      - final_metrics: the best metrics the loop produced (== baseline if
        nothing was accepted).
      - iterations_used: number of iterations executed.
      - candidates_tried: number of distinct candidates attempted.
      - accepted_count: number of candidates that passed the
        measurable-improvement gate.
      - status: COMPLETED / NO_IMPROVEMENT / BUDGET_EXHAUSTED / REPLAN_REQUIRED.
      - trace: tuple of (iteration, gap_class_or_sentinel, action_type, accepted)
        for offline replay and diagnostics.
    """

    final_metrics: CompilerMetrics
    iterations_used: int
    candidates_tried: int
    accepted_count: int
    status: LoopStatus
    trace: tuple[tuple[int, str, str, bool], ...] = ()


# Type alias for the gap classifier (default: classify_gap from gap_detector).
GapClassifier = Callable[[CompilerMetrics | None, CompilerMetrics], CompilerGapClass | str]


def _metrics_to_dict(m: CompilerMetrics) -> dict:
    return {
        "cycles": m.cycles,
        "reg_pressure": m.reg_pressure,
        "spills": m.spills,
        "energy_proxy": m.energy_proxy,
        "is_valid": m.is_valid,
    }


def _parse_metrics(payload: str) -> CompilerMetrics | None:
    """Parse a JSON-serialized CompilerMetrics dict. Returns None on failure."""
    try:
        d = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    try:
        return CompilerMetrics(
            cycles=int(d["cycles"]),
            reg_pressure=int(d["reg_pressure"]),
            spills=int(d["spills"]),
            energy_proxy=float(d["energy_proxy"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except (KeyError, TypeError, ValueError):
        return None


class CompilerOptimizationLoopUseCase:
    """Bounded compiler optimization loop with measurable-improvement gate.

    Usage::

        tool = CompilerToolStub()
        reg = ToolRegistry(); reg.register(tool)
        loop = CompilerOptimizationLoopUseCase(
            tool_registry=reg,
            policy=CompilerRepairPolicy.default_policy(),
            max_cycles=5,
        )
        result = loop.run(
            baseline=CompilerMetrics(...),
            candidates=[TransformParams(...), TransformParams(...)],
        )

    The loop applies at most one candidate per iteration; a candidate is
    rejected if it does not strictly beat the current best via
    :meth:`CompilerMetrics.better_than`.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        policy: CompilerRepairPolicy | None = None,
        *,
        max_cycles: int = 5,
        classifier: GapClassifier | None = None,
    ) -> None:
        self._registry = tool_registry or ToolRegistry()
        self._policy = policy or CompilerRepairPolicy.default_policy()
        self._max_cycles = max(1, max_cycles)
        self._classifier = classifier or classify_gap

    def _get_tool(self) -> ToolPort | None:
        return self._registry.get_by_capability(ToolCapability.COMPUTE)

    def run(
        self,
        baseline: CompilerMetrics,
        candidates: tuple[TransformParams, ...],
    ) -> CompilerLoopResult:
        """Run the bounded loop against ``candidates`` starting from ``baseline``.

        Returns a :class:`CompilerLoopResult` with the best metrics found,
        iteration count, and a per-iteration trace.

        Semantics: each iteration picks ``candidates[i]`` (in order), invokes
        the tool to produce ``new_metrics``, classifies the gap between
        ``current`` and ``new_metrics``, looks up the action via
        :class:`CompilerRepairPolicy`, and applies the measurable-improvement
        gate (:meth:`CompilerMetrics.better_than`). The loop returns
        :attr:`LoopStatus.COMPLETED` as soon as ANY candidate is accepted
        (i.e. strictly improves ``current``); it then stops — a successful
        improvement is the terminal event for this profile. The remaining
        candidates are not tried.
        """
        current = baseline
        accepted = 0
        iterations = 0
        candidates_tried = 0
        trace: list[tuple[int, str, str, bool]] = []

        for i in range(self._max_cycles):
            iterations = i + 1

            # No more candidates → break and report below.
            if i >= len(candidates):
                break

            candidate = candidates[i]
            candidates_tried += 1

            tool = self._get_tool()
            if tool is None:
                # No tool registered — cannot make progress.
                gap = self._classifier(current, current)
                action = self._policy.action_for(
                    gap if isinstance(gap, CompilerGapClass) else CompilerGapClass.MISSING_TRANSFORM
                )
                trace.append((i, str(gap), action.value, False))
                return CompilerLoopResult(
                    final_metrics=current,
                    iterations_used=iterations,
                    candidates_tried=candidates_tried,
                    accepted_count=accepted,
                    status=LoopStatus.NO_IMPROVEMENT,
                    trace=tuple(trace),
                )

            result = tool.invoke({
                "transform_type": candidate.transform_type.value,
                "params": {**candidate.params, "legal": candidate.legal},
                "baseline": _metrics_to_dict(current),
            })
            new_metrics = _parse_metrics(result.text) if result.success else None
            if new_metrics is None:
                # Tool failed or produced unparseable output — skip this candidate.
                gap = self._classifier(current, current)
                action = self._policy.action_for(
                    gap if isinstance(gap, CompilerGapClass) else CompilerGapClass.MISSING_TRANSFORM
                )
                trace.append((i, str(gap), action.value, False))
                continue

            # Classify the gap between current and what this candidate produced.
            gap = self._classifier(current, new_metrics)
            gap_for_policy = gap if isinstance(gap, CompilerGapClass) else CompilerGapClass.MISSING_TRANSFORM
            action = self._policy.action_for(gap_for_policy)

            # LOWERING_REPLAN terminates the loop — this profile cannot recover.
            if action is CompilerActionType.LOWERING_REPLAN:
                trace.append((i, str(gap), action.value, False))
                return CompilerLoopResult(
                    final_metrics=current,
                    iterations_used=iterations,
                    candidates_tried=candidates_tried,
                    accepted_count=accepted,
                    status=LoopStatus.REPLAN_REQUIRED,
                    trace=tuple(trace),
                )

            # Measurable-improvement gate: accept only if strictly better.
            if new_metrics.better_than(current):
                current = new_metrics
                accepted += 1
                trace.append((i, str(gap), action.value, True))
                # Terminal success: stop on first accepted candidate.
                return CompilerLoopResult(
                    final_metrics=current,
                    iterations_used=iterations,
                    candidates_tried=candidates_tried,
                    accepted_count=accepted,
                    status=LoopStatus.COMPLETED,
                    trace=tuple(trace),
                )

            # Rejected: record and continue to next candidate.
            trace.append((i, str(gap), action.value, False))

        # Loop exited without finding an accepted candidate.
        return CompilerLoopResult(
            final_metrics=current,
            iterations_used=iterations,
            candidates_tried=candidates_tried,
            accepted_count=accepted,
            status=LoopStatus.NO_IMPROVEMENT,
            trace=tuple(trace),
        )
