"""Tests for M054 S06 — ReactiveFrame + FrameBudget."""

from __future__ import annotations

import pytest

from active_skill_system.domain.reactive_frame import FrameBudget, ReactiveFrame

# ── FrameBudget ──────────────────────────────────────────────────────────


def test_frame_budget_defaults() -> None:
    b = FrameBudget()
    assert b.max_llm_calls is None
    assert b.llm_calls_used == 0
    assert b.is_exhausted is False


def test_frame_budget_record_llm_call() -> None:
    b = FrameBudget(max_llm_calls=3)
    b.record_llm_call()
    b.record_llm_call()
    assert b.llm_calls_used == 2
    assert b.is_exhausted is False
    b.record_llm_call()
    assert b.is_exhausted is True
    assert b.exhausted_by == "llm_calls"


def test_frame_budget_record_behavior_firing() -> None:
    b = FrameBudget(max_behavior_firings=2)
    b.record_behavior_firing()
    assert b.is_exhausted is False
    b.record_behavior_firing()
    assert b.is_exhausted is True
    assert b.exhausted_by == "behavior_firings"


def test_frame_budget_record_patch_proposal() -> None:
    b = FrameBudget(max_patch_proposals=1)
    b.record_patch_proposal()
    assert b.is_exhausted is True
    assert b.exhausted_by == "patch_proposals"


def test_frame_budget_unlimited_never_exhausted() -> None:
    b = FrameBudget()  # all None = unlimited
    for _ in range(100):
        b.record_llm_call()
        b.record_behavior_firing()
        b.record_patch_proposal()
    assert b.is_exhausted is False


def test_frame_budget_exhausted_by_empty_when_not_exhausted() -> None:
    b = FrameBudget(max_llm_calls=5)
    assert b.exhausted_by == ""


# ── ReactiveFrame ────────────────────────────────────────────────────────


def test_reactive_frame_creation_defaults() -> None:
    f = ReactiveFrame(goal="investigate claim")
    assert f.goal == "investigate claim"
    assert isinstance(f.budget, FrameBudget)
    assert f.behavior_names == ()
    assert f.policy_names == ()


def test_reactive_frame_rejects_empty_goal() -> None:
    with pytest.raises(ValueError, match="goal must be non-empty"):
        ReactiveFrame(goal="")


def test_reactive_frame_with_scoped_behaviors() -> None:
    f = ReactiveFrame(
        goal="test",
        behavior_names=("evidence_check", "gap_filler"),
    )
    assert f.is_behavior_active("evidence_check") is True
    assert f.is_behavior_active("gap_filler") is True
    assert f.is_behavior_active("other") is False


def test_reactive_frame_empty_behavior_names_all_active() -> None:
    """Empty behavior_names means ALL behaviors are active (no scoping)."""
    f = ReactiveFrame(goal="test", behavior_names=())
    assert f.is_behavior_active("any_behavior") is True


def test_reactive_frame_budget_exhausted_disables_behaviors() -> None:
    """When budget is exhausted, ALL behaviors become inactive."""
    budget = FrameBudget(max_behavior_firings=1)
    budget.record_behavior_firing()  # exhaust
    f = ReactiveFrame(goal="test", budget=budget, behavior_names=("evidence_check",))
    assert budget.is_exhausted is True
    assert f.is_behavior_active("evidence_check") is False


def test_reactive_frame_with_scoped_policies() -> None:
    f = ReactiveFrame(
        goal="test",
        policy_names=("auto_approve",),
    )
    assert f.is_policy_active("auto_approve") is True
    assert f.is_policy_active("manual_review") is False


def test_reactive_frame_empty_policy_names_all_active() -> None:
    f = ReactiveFrame(goal="test")
    assert f.is_policy_active("any_policy") is True


def test_reactive_frame_metadata() -> None:
    f = ReactiveFrame(
        goal="test",
        metadata={"priority": "high", "domain": "diligence"},
    )
    assert f.metadata["priority"] == "high"
    assert f.metadata["domain"] == "diligence"


def test_reactive_frame_budget_usage_during_run() -> None:
    """Simulate a run that uses budget."""
    budget = FrameBudget(max_llm_calls=2, max_behavior_firings=3)
    f = ReactiveFrame(goal="investigate", budget=budget)

    # Behaviors active at start.
    assert f.is_behavior_active("evidence_check") is True

    # Use some budget.
    budget.record_llm_call()
    budget.record_behavior_firing()
    assert f.is_behavior_active("evidence_check") is True  # still active

    # Exhaust LLM budget.
    budget.record_llm_call()
    assert budget.is_exhausted is True
    assert f.is_behavior_active("evidence_check") is False  # now inactive
