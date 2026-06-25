"""Unit tests for SQLRepairPolicy (M018 S02)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from active_skill_system.application.use_cases.sql_repair_policy import SQLRepairPolicy
from active_skill_system.domain.sql_types import SQLActionType, SQLGapClass

# ── Default mapping ───────────────────────────────────────────────────────


def test_default_policy_maps_every_gap_class() -> None:
    policy = SQLRepairPolicy.default_policy()
    # All 5 SQLGapClass values must be covered.
    for gap in SQLGapClass:
        assert policy.covers(gap), f"default policy missing {gap}"
        action = policy.action_for(gap)
        assert isinstance(action, SQLActionType)


def test_default_policy_specific_mappings() -> None:
    """Verify the specific 5->4 mapping documented in sql_repair_policy.py."""
    policy = SQLRepairPolicy.default_policy()
    assert policy.action_for(SQLGapClass.MISSING_INDEX) is SQLActionType.ADD_INDEX
    assert policy.action_for(SQLGapClass.FULL_TABLE_SCAN) is SQLActionType.ADD_INDEX
    assert policy.action_for(SQLGapClass.WRONG_JOIN_ORDER) is SQLActionType.REORDER_JOINS
    assert policy.action_for(SQLGapClass.INEFFICIENT_AGGREGATE) is SQLActionType.REWRITE_AS_JOIN
    assert policy.action_for(SQLGapClass.COST_REGRESSION) is SQLActionType.REPLAN_QUERY


def test_default_policy_uses_all_four_action_types() -> None:
    """The 5->4 mapping must touch every SQLActionType."""
    policy = SQLRepairPolicy.default_policy()
    actions_used = {policy.action_for(g) for g in SQLGapClass}
    assert len(actions_used) == 4
    assert actions_used == set(SQLActionType)


# ── Fallback semantics ────────────────────────────────────────────────────


def test_action_for_falls_back_to_replan_query() -> None:
    """Unknown gap (not in mapping) must fall back to REPLAN_QUERY (safe default, not REWRITE_AS_JOIN)."""
    policy = SQLRepairPolicy(mapping={SQLGapClass.MISSING_INDEX: SQLActionType.ADD_INDEX})
    # WRONG_JOIN_ORDER is not in this minimal mapping; fallback must be REPLAN_QUERY.
    assert policy.action_for(SQLGapClass.WRONG_JOIN_ORDER) is SQLActionType.REPLAN_QUERY


# ── Covers ────────────────────────────────────────────────────────────────


def test_covers_returns_true_for_explicit_mappings() -> None:
    policy = SQLRepairPolicy.default_policy()
    assert policy.covers(SQLGapClass.MISSING_INDEX) is True


def test_covers_returns_false_for_missing_mappings() -> None:
    policy = SQLRepairPolicy(mapping={SQLGapClass.MISSING_INDEX: SQLActionType.ADD_INDEX})
    assert policy.covers(SQLGapClass.COST_REGRESSION) is False


# ── Frozen semantics ──────────────────────────────────────────────────────


def test_sql_repair_policy_is_frozen() -> None:
    """Frozen dataclass: cannot mutate mapping after construction."""
    policy = SQLRepairPolicy.default_policy()
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError
        policy.mapping = {SQLGapClass.MISSING_INDEX: SQLActionType.REPLAN_QUERY}  # type: ignore[misc]


# ── Validation ────────────────────────────────────────────────────────────


def test_empty_mapping_rejected() -> None:
    with pytest.raises(ValueError, match="mapping must be non-empty"):
        SQLRepairPolicy(mapping={})


def test_non_dict_mapping_rejected() -> None:
    with pytest.raises(ValueError, match="mapping must be a dict"):
        SQLRepairPolicy(mapping=[("key", "value")])  # type: ignore[arg-type]


def test_invalid_key_rejected() -> None:
    with pytest.raises(ValueError, match="mapping key must be a SQLGapClass"):
        SQLRepairPolicy(mapping={"MISSING_INDEX": SQLActionType.ADD_INDEX})  # type: ignore[dict-item]


def test_invalid_value_rejected() -> None:
    with pytest.raises(ValueError, match="mapping value must be a SQLActionType"):
        SQLRepairPolicy(mapping={SQLGapClass.MISSING_INDEX: "ADD_INDEX"})  # type: ignore[dict-item]


# ── Decoupling from reasoning/compiler RepairPolicy ──────────────────────


def test_separate_from_reasoning_and_compiler_repair_policy() -> None:
    """SQLRepairPolicy must not import reasoning RepairPolicy or compiler RepairPolicy.

    Decoupling enforced by grepping the source for forbidden imports.
    """
    mod = importlib.import_module("active_skill_system.application.use_cases.sql_repair_policy")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    forbidden = (
        "from active_skill_system.application.use_cases.repair_policy",
        "import active_skill_system.application.use_cases.repair_policy",
        "from active_skill_system.application.use_cases.compiler_repair_policy",
        "import active_skill_system.application.use_cases.compiler_repair_policy",
    )
    for f in forbidden:
        assert f not in src, (
            f"sql_repair_policy.py must not contain '{f}' (decoupling from other domain policies)"
        )


# ── R002: module infra-free ────────────────────────────────────────────────


def test_module_infra_free() -> None:
    """sql_repair_policy.py must not import activegraph / anthropic / openai (R002)."""
    mod = importlib.import_module("active_skill_system.application.use_cases.sql_repair_policy")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, (
            f"sql_repair_policy.py must not contain '{forbidden}' (R002)"
        )


# ── Coverage diagnostic for EvolutionEngine ───────────────────────────────


def test_covers_supports_evolution_engine_diagnostics() -> None:
    """A custom policy can report coverage gaps for offline EvolutionEngine tuning."""
    partial = SQLRepairPolicy(mapping={
        SQLGapClass.MISSING_INDEX: SQLActionType.ADD_INDEX,
    })
    # Only 1 of 5 gap classes is covered — useful diagnostic for EvolutionEngine.
    coverage = sum(1 for gap in SQLGapClass if partial.covers(gap))
    assert coverage == 1
