"""L1 Domain - Governance policy (extended M014 S02).

GovernancePolicy captures the policy constraints a runtime must enforce:
max evolution depth, review threshold, frozen flag, and safety level
(L1/L2/L3 from D006/D007 loop engineering synthesis). ApprovalRequest
handles the F-14 approval workflow for irreversible actions.

Pure domain. NO I/O, NO infrastructure imports (R002). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class SafetyLevel(StrEnum):
    """Graduated autonomy level (D006 loop engineering, D007 Synapse).

    L1: report-only — no side effects, human reviews and decides.
    L2: fork + review — changes in isolated worktree, human approves before merge.
    L3: auto-apply — system applies if measurable-improvement gate passes.
    """

    L1_REPORT = "L1_report"
    L2_FORK_REVIEW = "L2_fork_review"
    L3_AUTO_APPLY = "L3_auto_apply"


class ApprovalStatus(StrEnum):
    """Lifecycle status of an approval request (F-14)."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def _max_evolution_depth_positive(p: GovernancePolicy) -> None:
    if not isinstance(p.max_evolution_depth, int) or isinstance(p.max_evolution_depth, bool):
        raise ValueError(
            f"GovernancePolicy.max_evolution_depth must be an int (got "
            f"{type(p.max_evolution_depth).__name__})"
        )
    if p.max_evolution_depth < 1:
        raise ValueError(
            f"GovernancePolicy.max_evolution_depth must be >= 1 (got {p.max_evolution_depth})"
        )


def _review_threshold_in_unit_interval(p: GovernancePolicy) -> None:
    if not isinstance(p.review_threshold, (int, float)):
        raise ValueError(
            f"GovernancePolicy.review_threshold must be a number (got "
            f"{type(p.review_threshold).__name__})"
        )
    if not (0.0 <= float(p.review_threshold) <= 1.0):
        raise ValueError(
            f"GovernancePolicy.review_threshold must be in [0.0, 1.0] (got {p.review_threshold!r})"
        )


@dataclass(frozen=True)
class GovernancePolicy:
    """Policy constraints enforced by the runtime.

    Carries:
      - max_evolution_depth: int >= 1 (max generations).
      - review_threshold: float in [0.0, 1.0] (fitness below which
        human review is required).
      - frozen: bool (when True, the runtime rejects any further mutations).
      - safety_level: SafetyLevel (graduated autonomy, default L1_REPORT).
    """

    max_evolution_depth: int
    review_threshold: float
    frozen: bool = False
    safety_level: SafetyLevel = SafetyLevel.L1_REPORT

    def __post_init__(self) -> None:
        errors: list[str] = []
        for check in (_max_evolution_depth_positive, _review_threshold_in_unit_interval):
            try:
                check(self)
            except ValueError as e:
                errors.append(str(e))
        if not isinstance(self.safety_level, SafetyLevel):
            errors.append(
                f"safety_level must be a SafetyLevel (got {type(self.safety_level).__name__})"
            )
        if errors:
            raise ValueError("GovernancePolicy invariant violation: " + "; ".join(errors))

    @classmethod
    def default_policy(cls) -> GovernancePolicy:
        """Return a sensible default (depth=5, threshold=0.7, not frozen, L1)."""
        return cls(
            max_evolution_depth=5, review_threshold=0.7, frozen=False,
            safety_level=SafetyLevel.L1_REPORT,
        )


@dataclass(frozen=True)
class ApprovalRequest:
    """A request for human approval of an irreversible action (F-14).

    Carries:
      - action_id: unique identifier for the action.
      - action_type: what kind of action (e.g. "delete", "merge", "deploy").
      - reason: why the action is needed.
      - status: ApprovalStatus (PENDING by default).
      - requested_at: UTC timestamp.
    """

    action_id: str
    action_type: str
    reason: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = datetime.now(UTC)  # noqa: RUF009

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.action_id, str) or not self.action_id.strip():
            errors.append(f"action_id must be a non-empty string (got {self.action_id!r})")
        if not isinstance(self.action_type, str) or not self.action_type.strip():
            errors.append(f"action_type must be a non-empty string (got {self.action_type!r})")
        if not isinstance(self.reason, str) or not self.reason.strip():
            errors.append(f"reason must be a non-empty string (got {self.reason!r})")
        if not isinstance(self.status, ApprovalStatus):
            errors.append(f"status must be an ApprovalStatus (got {type(self.status).__name__})")
        if errors:
            raise ValueError("ApprovalRequest invariant violation: " + "; ".join(errors))

    def with_status(self, status: ApprovalStatus) -> ApprovalRequest:
        """Return a new ApprovalRequest with updated status."""
        return ApprovalRequest(
            action_id=self.action_id,
            action_type=self.action_type,
            reason=self.reason,
            status=status,
            requested_at=self.requested_at,
        )
