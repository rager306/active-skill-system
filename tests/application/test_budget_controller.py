"""Unit tests for BudgetController (M013 S02)."""

from __future__ import annotations

import pytest

from active_skill_system.application.budget_controller import (
    BudgetController,
    BudgetExhausted,
)


def test_within_budget_not_exhausted() -> None:
    ctrl = BudgetController(max_llm_calls=10)
    ctrl.track(llm_calls=3)
    assert ctrl.is_exhausted() is False


def test_over_budget_exhausted() -> None:
    ctrl = BudgetController(max_llm_calls=5)
    ctrl.track(llm_calls=5)
    assert ctrl.is_exhausted() is True


def test_remaining_correct() -> None:
    ctrl = BudgetController(max_llm_calls=10, max_tool_calls=5)
    ctrl.track(llm_calls=3, tool_calls=1)
    rem = ctrl.remaining()
    assert rem["llm_calls"] == 7
    assert rem["tool_calls"] == 4


def test_enforce_raises_when_exhausted() -> None:
    ctrl = BudgetController(max_llm_calls=2)
    ctrl.track(llm_calls=2)
    with pytest.raises(BudgetExhausted, match="llm_calls"):
        ctrl.enforce()


def test_enforce_does_not_raise_when_within_budget() -> None:
    ctrl = BudgetController(max_llm_calls=10)
    ctrl.track(llm_calls=3)
    ctrl.enforce()  # should not raise


def test_multiple_resource_types() -> None:
    ctrl = BudgetController(max_llm_calls=5, max_tool_calls=3, max_cost_usd=1.0)
    ctrl.track(llm_calls=2, tool_calls=1, cost_usd=0.5)
    assert ctrl.is_exhausted() is False
    ctrl.track(cost_usd=0.6)
    assert ctrl.is_exhausted() is True  # cost exceeded


def test_zero_budget_immediate_exhaustion() -> None:
    ctrl = BudgetController(max_llm_calls=0)
    assert ctrl.is_exhausted() is True


def test_no_limit_never_exhausted() -> None:
    ctrl = BudgetController()  # all None
    ctrl.track(llm_calls=1000, tool_calls=500, cost_usd=999.0)
    assert ctrl.is_exhausted() is False


def test_used_property() -> None:
    ctrl = BudgetController(max_llm_calls=10)
    ctrl.track(llm_calls=3, tool_calls=2, cost_usd=0.5)
    used = ctrl.used
    assert used["llm_calls"] == 3
    assert used["tool_calls"] == 2
    assert used["cost_usd"] == 0.5


def test_remaining_none_for_unlimited() -> None:
    ctrl = BudgetController(max_llm_calls=10)  # tool/cost unlimited
    rem = ctrl.remaining()
    assert rem["llm_calls"] == 10
    assert rem["tool_calls"] is None
    assert rem["cost_usd"] is None
