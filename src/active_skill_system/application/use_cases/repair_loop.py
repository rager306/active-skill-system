"""L2 Application use-case — RepairLoopUseCase (M009 S02).

The bounded repair loop (concept.md §5, §6.1, §7):

    validate → (gaps?) → classify (highest priority) → choose action
    → execute → produce GraphPatch → apply + check measurable-improvement
    → accept (graph = patched) OR reject (rollback) → re-validate → loop

Mandatory limiters (concept.md §7):
  - max_cycles enforced (budget)
  - loop-detection (fingerprint of node/edge counts; repeats skipped)
  - measurable-improvement gate (patch accepted only if it improves)

Action execution is injected via ``execute_action`` callback, so the loop
is testable with fake actions (no tools needed — S03 wires real tools).

Pure application. Depends on domain + validator (M003); no I/O (R002).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from active_skill_system.application.use_cases.repair_policy import (
    RepairPolicy,
)
from active_skill_system.application.use_cases.validate_task_graph import (
    ValidateTaskGraphUseCase,
)
from active_skill_system.domain.runtime.gap import (
    GapClass,
    GapClassification,
    Severity,
    severity_rank,
)
from active_skill_system.domain.runtime.graph import TaskGraph
from active_skill_system.domain.runtime.nodes import TaskNodeId
from active_skill_system.domain.runtime.patch import (
    GraphPatch,
    is_measurable_improvement,
)

# Type alias for the action-execution callback injected into the loop.
# Returns a GraphPatch (to apply) or None (no patch / action couldn't help).
ExecuteAction = Callable[[GapClassification, TaskGraph], "GraphPatch | None"]


class RepairStatus(StrEnum):
    """Outcome of the repair loop."""

    COMPLETED = "completed"  # all gaps closed
    PARTIAL = "partial"  # budget exhausted or some gaps remain
    FAILED = "failed"  # all patches rejected


@dataclass(frozen=True)
class RepairResult:
    """Result of running the repair loop.

    Carries:
      - final_graph: the graph after the loop (may have remaining gaps).
      - cycles_used: number of repair cycles executed.
      - gaps_remaining: count of gaps still in the graph.
      - patches_accepted / patches_rejected: counts.
      - status: completed / partial / failed.
      - actions_taken: tuple of (cycle, gap_class, action_type, accepted).
    """

    final_graph: TaskGraph
    cycles_used: int
    gaps_remaining: int
    patches_accepted: int
    patches_rejected: int
    status: RepairStatus
    actions_taken: tuple[tuple[int, str, str, bool], ...] = ()


class RepairLoopUseCase:
    """Bounded repair loop with measurable-improvement gate.

    Usage::

        validator = ValidateTaskGraphUseCase()
        policy = RepairPolicy.default_policy()
        loop = RepairLoopUseCase(validator, policy, max_cycles=5)
        result = loop.run(graph, execute_action=my_action_executor)
    """

    def __init__(
        self,
        validator: ValidateTaskGraphUseCase | None = None,
        policy: RepairPolicy | None = None,
        *,
        max_cycles: int = 5,
    ) -> None:
        self._validator = validator or ValidateTaskGraphUseCase()
        self._policy = policy or RepairPolicy.default_policy()
        self._max_cycles = max(1, max_cycles)

    def run(
        self,
        graph: TaskGraph,
        execute_action: ExecuteAction,
    ) -> RepairResult:
        """Run the bounded repair loop on ``graph``.

        Args:
            graph: the initial TaskGraph (may have gaps).
            execute_action: callback that takes (gap_classification, graph)
                and returns a GraphPatch or None.

        Returns:
            RepairResult with the final graph and loop statistics.
        """
        current = graph
        cycles = 0
        accepted = 0
        rejected = 0
        actions: list[tuple[int, str, str, bool]] = []
        seen_fingerprints: set[tuple[int, int]] = set()

        while cycles < self._max_cycles:
            report = self._validator.validate(current)

            # No gaps → done.
            if not report.gaps:
                return RepairResult(
                    final_graph=current,
                    cycles_used=cycles,
                    gaps_remaining=0,
                    patches_accepted=accepted,
                    patches_rejected=rejected,
                    status=RepairStatus.COMPLETED,
                    actions_taken=tuple(actions),
                )

            # Pick highest-priority gap (lowest severity_rank = most critical).
            gap_classifications = _classify_gaps(report)
            if not gap_classifications:
                # Gaps exist but couldn't classify — partial.
                break

            gap = min(gap_classifications, key=lambda g: severity_rank(g.severity))
            action_type = self._policy.action_for(gap.gap_class)

            # Execute the repair action → produce a GraphPatch (or None).
            patch = execute_action(gap, current)
            if patch is None:
                # Action couldn't help; record and continue to next cycle.
                actions.append((cycles, gap.gap_class.value, action_type.value, False))
                cycles += 1
                continue

            # Loop-detection: if graph fingerprint seen before (after a real
            # patch attempt), skip — we're in a cycle of non-improving patches.
            fingerprint = (len(current.nodes), len(current.edges))
            if fingerprint in seen_fingerprints:
                break
            seen_fingerprints.add(fingerprint)

            # Apply the patch and check measurable improvement.
            candidate = patch.apply(current)
            candidate_report = self._validator.validate(candidate)
            improved = is_measurable_improvement(
                gaps_before=len(report.gaps),
                gaps_after=len(candidate_report.gaps),
                constraints_before=len(report.constraint_violations),
                constraints_after=len(candidate_report.constraint_violations),
                verified_before=len(report.supported_goal_ids),
                verified_after=len(candidate_report.supported_goal_ids),
            )

            if improved:
                current = candidate
                accepted += 1
                actions.append((cycles, gap.gap_class.value, action_type.value, True))
            else:
                rejected += 1
                actions.append((cycles, gap.gap_class.value, action_type.value, False))

            cycles += 1

        # Budget exhausted or loop detected — compute final state.
        final_report = self._validator.validate(current)
        remaining = len(final_report.gaps)
        status = RepairStatus.FAILED if (accepted == 0 and rejected > 0) else RepairStatus.PARTIAL

        return RepairResult(
            final_graph=current,
            cycles_used=cycles,
            gaps_remaining=remaining,
            patches_accepted=accepted,
            patches_rejected=rejected,
            status=status,
            actions_taken=tuple(actions),
        )


def _classify_gaps(report) -> list[GapClassification]:  # noqa: ANN001
    """Classify each gap in the validation report into a GapClassification.

    The classification is heuristic for M009: unsupported goals →
    MISSING_EVIDENCE (the most common gap type), explicit Gap nodes →
    MISSING_EVIDENCE too. A more sophisticated classifier can be injected
    later (concept.md §7 full gap table).
    """
    classifications: list[GapClassification] = []
    for gap_info in report.gaps:
        node_id = TaskNodeId(gap_info.node_id)
        classifications.append(
            GapClassification(
                node_id=node_id,
                gap_class=GapClass.MISSING_EVIDENCE,
                severity=Severity.HIGH,
                proposed_action="search",
            )
        )
    return classifications
