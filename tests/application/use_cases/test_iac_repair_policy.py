"""Tests for IaCRepairPolicy (M023 S02)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from active_skill_system.application.use_cases.iac_repair_policy import IaCRepairPolicy
from active_skill_system.domain.iac_types import IaCActionType, IaCGapClass

# ── Default mapping ───────────────────────────────────────────────────────


def test_default_policy_maps_every_gap_class() -> None:
    policy = IaCRepairPolicy.default_policy()
    for gap in IaCGapClass:
        assert policy.covers(gap), f"default policy missing {gap}"


def test_default_policy_specific_mappings() -> None:
    policy = IaCRepairPolicy.default_policy()
    assert policy.action_for(IaCGapClass.UNUSED_VARIABLE) is IaCActionType.REMOVE_UNUSED
    assert policy.action_for(IaCGapClass.MISSING_OUTPUT) is IaCActionType.ADD_OUTPUT
    assert policy.action_for(IaCGapClass.CIRCULAR_DEPENDENCY) is IaCActionType.RESTRUCTURE_DEP
    assert policy.action_for(IaCGapClass.DRIFT_DETECTED) is IaCActionType.REPLAN_PROVIDERS
    assert policy.action_for(IaCGapClass.COST_REGRESSION) is IaCActionType.REPLAN_PROVIDERS


def test_default_policy_uses_all_four_action_types() -> None:
    policy = IaCRepairPolicy.default_policy()
    actions_used = {policy.action_for(g) for g in IaCGapClass}
    assert len(actions_used) == 4
    assert actions_used == set(IaCActionType)


# ── Fallback semantics ────────────────────────────────────────────────────


def test_action_for_falls_back_to_replan_providers() -> None:
    policy = IaCRepairPolicy(mapping={IaCGapClass.UNUSED_VARIABLE: IaCActionType.REMOVE_UNUSED})
    assert policy.action_for(IaCGapClass.COST_REGRESSION) is IaCActionType.REPLAN_PROVIDERS


# ── Covers ────────────────────────────────────────────────────────────────


def test_covers_returns_true_for_explicit_mappings() -> None:
    policy = IaCRepairPolicy.default_policy()
    assert policy.covers(IaCGapClass.UNUSED_VARIABLE)


def test_covers_returns_false_for_missing_mappings() -> None:
    policy = IaCRepairPolicy(mapping={IaCGapClass.UNUSED_VARIABLE: IaCActionType.REMOVE_UNUSED})
    assert policy.covers(IaCGapClass.COST_REGRESSION) is False


# ── Frozen semantics ──────────────────────────────────────────────────────


def test_iac_repair_policy_is_frozen() -> None:
    policy = IaCRepairPolicy.default_policy()
    with pytest.raises((AttributeError, Exception)):
        policy.mapping = {IaCGapClass.UNUSED_VARIABLE: IaCActionType.REPLAN_PROVIDERS}  # type: ignore[misc]


# ── Validation ────────────────────────────────────────────────────────────


def test_empty_mapping_rejected() -> None:
    with pytest.raises(ValueError, match="mapping must be non-empty"):
        IaCRepairPolicy(mapping={})


def test_invalid_key_rejected() -> None:
    with pytest.raises(ValueError, match="mapping key must be a IaCGapClass"):
        IaCRepairPolicy(mapping={"UNUSED_VARIABLE": IaCActionType.REMOVE_UNUSED})  # type: ignore[dict-item]


def test_invalid_value_rejected() -> None:
    with pytest.raises(ValueError, match="mapping value must be a IaCActionType"):
        IaCRepairPolicy(mapping={IaCGapClass.UNUSED_VARIABLE: "REMOVE_UNUSED"})  # type: ignore[dict-item]


# ── Decoupling ────────────────────────────────────────────────────────────


def test_separate_from_reasoning_compiler_and_sql_repair_policy() -> None:
    mod = importlib.import_module("active_skill_system.application.use_cases.iac_repair_policy")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    forbidden = (
        "from active_skill_system.application.use_cases.repair_policy",
        "from active_skill_system.application.use_cases.compiler_repair_policy",
        "from active_skill_system.application.use_cases.sql_repair_policy",
    )
    for f in forbidden:
        assert f not in src, f"iac_repair_policy.py must not import {f!r}"


# ── R002 ────────────────────────────────────────────────────────────────


def test_module_infra_free() -> None:
    mod = importlib.import_module("active_skill_system.application.use_cases.iac_repair_policy")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src
