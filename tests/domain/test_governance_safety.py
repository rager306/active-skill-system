"""Unit tests for SafetyLevel + ApprovalRequest (M014 S02)."""

from __future__ import annotations

import pytest

from active_skill_system.domain.governance import (
    ApprovalRequest,
    ApprovalStatus,
    GovernancePolicy,
    SafetyLevel,
)


def test_safety_level_all_three_values() -> None:
    assert {s.value for s in SafetyLevel} == {"L1_report", "L2_fork_review", "L3_auto_apply"}


def test_governance_default_has_l1_safety() -> None:
    p = GovernancePolicy.default_policy()
    assert p.safety_level is SafetyLevel.L1_REPORT


def test_governance_custom_safety_l2() -> None:
    p = GovernancePolicy(
        max_evolution_depth=3, review_threshold=0.8,
        safety_level=SafetyLevel.L2_FORK_REVIEW,
    )
    assert p.safety_level is SafetyLevel.L2_FORK_REVIEW


def test_governance_custom_safety_l3() -> None:
    p = GovernancePolicy(
        max_evolution_depth=3, review_threshold=0.9,
        safety_level=SafetyLevel.L3_AUTO_APPLY,
    )
    assert p.safety_level is SafetyLevel.L3_AUTO_APPLY


def test_approval_request_constructs() -> None:
    a = ApprovalRequest(action_id="a1", action_type="delete", reason="cleanup")
    assert a.status is ApprovalStatus.PENDING
    assert a.action_type == "delete"


def test_approval_request_rejects_empty_action_id() -> None:
    with pytest.raises(ValueError, match="action_id"):
        ApprovalRequest(action_id="", action_type="x", reason="y")


def test_approval_request_rejects_empty_action_type() -> None:
    with pytest.raises(ValueError, match="action_type"):
        ApprovalRequest(action_id="a1", action_type="", reason="y")


def test_approval_request_rejects_empty_reason() -> None:
    with pytest.raises(ValueError, match="reason"):
        ApprovalRequest(action_id="a1", action_type="delete", reason="")


def test_approval_with_status_approved() -> None:
    a = ApprovalRequest(action_id="a1", action_type="deploy", reason="release")
    approved = a.with_status(ApprovalStatus.APPROVED)
    assert approved.status is ApprovalStatus.APPROVED
    assert a.status is ApprovalStatus.PENDING  # original unchanged


def test_approval_with_status_rejected() -> None:
    a = ApprovalRequest(action_id="a1", action_type="deploy", reason="release")
    rejected = a.with_status(ApprovalStatus.REJECTED)
    assert rejected.status is ApprovalStatus.REJECTED


def test_governance_rejects_invalid_safety_level() -> None:
    with pytest.raises(ValueError, match="safety_level"):
        GovernancePolicy(
            max_evolution_depth=3, review_threshold=0.5,
            safety_level="bogus",  # type: ignore[arg-type]
        )
