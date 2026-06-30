"""L2 Application — ForkAnalysis use case (M054 S12).

Given a fork + diff (M052), analyzes WHY the fork diverged at the reactive
layer. Uses EventStore audit trail (M053 S10) to identify which behavior
fired differently, which patch was proposed/rejected, which policy decision
differed.

Answers 'why did fork B produce different output?' at the reactive level —
not just WHAT diverged (structural diff), but WHY (which reactive decisions
differed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from active_skill_system.application.ports.event_store import EventStore
from active_skill_system.domain.fork import Diff


@dataclass(frozen=True)
class ReactiveDivergence:
    """Reactive-level divergence between parent and fork runs.

    Fields:
      - behavior_firings_diff: behaviors that fired differently.
        Dict of behavior_name -> (parent_count, fork_count).
      - patch_proposals_diff: patches proposed differently.
        Dict of proposed_by -> (parent_count, fork_count).
      - policy_decisions_diff: policy decisions that differed.
        Dict of proposal_id -> (parent_decision, fork_decision).
      - pattern_matches_diff: pattern triggers that differed.
        Dict of pattern_name -> (parent_count, fork_count).
    """

    behavior_firings_diff: dict[str, tuple[int, int]] = field(default_factory=dict)
    patch_proposals_diff: dict[str, tuple[int, int]] = field(default_factory=dict)
    policy_decisions_diff: dict[str, tuple[str, str]] = field(default_factory=dict)
    pattern_matches_diff: dict[str, tuple[int, int]] = field(default_factory=dict)

    @property
    def has_divergence(self) -> bool:
        """True if any reactive divergence was found."""
        return bool(
            self.behavior_firings_diff
            or self.patch_proposals_diff
            or self.policy_decisions_diff
            or self.pattern_matches_diff
        )

    def summary(self) -> str:
        """Human-readable summary of reactive divergence."""
        lines: list[str] = []
        if self.behavior_firings_diff:
            lines.append("Behavior firing differences:")
            for name, (parent, fork) in self.behavior_firings_diff.items():
                lines.append(f"  {name}: parent={parent} fork={fork}")
        if self.patch_proposals_diff:
            lines.append("Patch proposal differences:")
            for name, (parent, fork) in self.patch_proposals_diff.items():
                lines.append(f"  {name}: parent={parent} fork={fork}")
        if self.policy_decisions_diff:
            lines.append("Policy decision differences:")
            for pid, (parent, fork) in self.policy_decisions_diff.items():
                lines.append(f"  {pid}: parent={parent} fork={fork}")
        if not lines:
            lines.append("No reactive divergence detected (structural diff only).")
        return "\n".join(lines)


@dataclass(frozen=True)
class ForkAnalysis:
    """Full analysis of why a fork diverged.

    Fields:
      - parent_run_id: the source run.
      - fork_run_id: the forked run.
      - structural_diff: the structural Diff (from ForkEngine).
      - reactive_divergence: the reactive-level divergence analysis.
      - split_event_id: where the runs diverged.
    """

    parent_run_id: str
    fork_run_id: str
    structural_diff: Diff | None = None
    reactive_divergence: ReactiveDivergence = field(default_factory=ReactiveDivergence)
    split_event_id: str = ""

    def summary(self) -> str:
        """Human-readable full analysis."""
        lines = [
            f"ForkAnalysis: {self.parent_run_id} vs {self.fork_run_id}",
            f"  Split at: {self.split_event_id or '(no divergence)'}",
        ]
        if self.structural_diff:
            lines.append(f"  Structural: {len(self.structural_diff.divergent_objects)} divergent objects")
        lines.append("  Reactive:")
        for line in self.reactive_divergence.summary().splitlines():
            lines.append(f"    {line}")
        return "\n".join(lines)


class ForkAnalysisUseCase:
    """Analyze why a fork diverged at the reactive level.

    Args:
        event_store: source of reactive audit events for both runs.
    """

    def __init__(self, event_store: EventStore) -> None:
        if event_store is None:
            raise TypeError("event_store must be a non-None EventStore")
        self._store = event_store

    def analyze(
        self,
        parent_run_id: str,
        fork_run_id: str,
        structural_diff: Diff | None = None,
    ) -> ForkAnalysis:
        """Analyze reactive divergence between parent and fork.

        Args:
            parent_run_id: the source run.
            fork_run_id: the forked run.
            structural_diff: optional structural Diff from ForkEngine.

        Returns:
            ForkAnalysis with reactive divergence breakdown.
        """
        parent_events = list(self._store.iter_events(run_id=parent_run_id))
        fork_events = list(self._store.iter_events(run_id=fork_run_id))

        # Analyze behavior firing differences.
        behavior_firings = self._count_by_behavior(parent_events, fork_events)

        # Analyze patch proposal differences.
        patch_proposals = self._count_by_proposer(parent_events, fork_events)

        # Analyze policy decision differences.
        policy_decisions = self._policy_decisions(parent_events, fork_events)

        # Analyze pattern match differences.
        pattern_matches = self._count_patterns(parent_events, fork_events)

        reactive = ReactiveDivergence(
            behavior_firings_diff=behavior_firings,
            patch_proposals_diff=patch_proposals,
            policy_decisions_diff=policy_decisions,
            pattern_matches_diff=pattern_matches,
        )

        split_event_id = ""
        if structural_diff is not None:
            split_event_id = structural_diff.split_event_id

        return ForkAnalysis(
            parent_run_id=parent_run_id,
            fork_run_id=fork_run_id,
            structural_diff=structural_diff,
            reactive_divergence=reactive,
            split_event_id=split_event_id,
        )

    def _count_by_behavior(
        self, parent_events: list[Any], fork_events: list[Any],
    ) -> dict[str, tuple[int, int]]:
        """Count behavior.triggered events by behavior_name."""
        parent_counts: dict[str, int] = {}
        fork_counts: dict[str, int] = {}

        for event in parent_events:
            if event.type == "behavior.triggered":
                name = event.payload.get("behavior_name", "unknown")
                parent_counts[name] = parent_counts.get(name, 0) + 1

        for event in fork_events:
            if event.type == "behavior.triggered":
                name = event.payload.get("behavior_name", "unknown")
                fork_counts[name] = fork_counts.get(name, 0) + 1

        all_names = set(parent_counts.keys()) | set(fork_counts.keys())
        return {
            name: (parent_counts.get(name, 0), fork_counts.get(name, 0))
            for name in all_names
            if parent_counts.get(name, 0) != fork_counts.get(name, 0)
        }

    def _count_by_proposer(
        self, parent_events: list[Any], fork_events: list[Any],
    ) -> dict[str, tuple[int, int]]:
        """Count patch.proposed events by proposed_by."""
        parent_counts: dict[str, int] = {}
        fork_counts: dict[str, int] = {}

        for event in parent_events:
            if event.type == "patch.proposed":
                name = event.payload.get("proposed_by", "unknown")
                parent_counts[name] = parent_counts.get(name, 0) + 1

        for event in fork_events:
            if event.type == "patch.proposed":
                name = event.payload.get("proposed_by", "unknown")
                fork_counts[name] = fork_counts.get(name, 0) + 1

        all_names = set(parent_counts.keys()) | set(fork_counts.keys())
        return {
            name: (parent_counts.get(name, 0), fork_counts.get(name, 0))
            for name in all_names
            if parent_counts.get(name, 0) != fork_counts.get(name, 0)
        }

    def _policy_decisions(
        self, parent_events: list[Any], fork_events: list[Any],
    ) -> dict[str, tuple[str, str]]:
        """Compare policy.approved/rejected decisions by proposal_id."""
        parent_decisions: dict[str, str] = {}
        fork_decisions: dict[str, str] = {}

        for event in parent_events:
            if event.type in ("policy.approved", "policy.rejected"):
                pid = event.payload.get("proposal_id", "")
                parent_decisions[pid] = event.type

        for event in fork_events:
            if event.type in ("policy.approved", "policy.rejected"):
                pid = event.payload.get("proposal_id", "")
                fork_decisions[pid] = event.type

        all_ids = set(parent_decisions.keys()) | set(fork_decisions.keys())
        return {
            pid: (parent_decisions.get(pid, "none"), fork_decisions.get(pid, "none"))
            for pid in all_ids
            if parent_decisions.get(pid) != fork_decisions.get(pid)
        }

    def _count_patterns(
        self, parent_events: list[Any], fork_events: list[Any],
    ) -> dict[str, tuple[int, int]]:
        """Count pattern.matched events by pattern_name."""
        parent_counts: dict[str, int] = {}
        fork_counts: dict[str, int] = {}

        for event in parent_events:
            if event.type == "pattern.matched":
                name = event.payload.get("pattern_name", "unknown")
                parent_counts[name] = parent_counts.get(name, 0) + 1

        for event in fork_events:
            if event.type == "pattern.matched":
                name = event.payload.get("pattern_name", "unknown")
                fork_counts[name] = fork_counts.get(name, 0) + 1

        all_names = set(parent_counts.keys()) | set(fork_counts.keys())
        return {
            name: (parent_counts.get(name, 0), fork_counts.get(name, 0))
            for name in all_names
            if parent_counts.get(name, 0) != fork_counts.get(name, 0)
        }
