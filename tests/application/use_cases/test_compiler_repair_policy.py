"""Unit tests for CompilerRepairPolicy (M016 S02)."""

from __future__ import annotations

import pytest

from active_skill_system.application.use_cases.compiler_repair_policy import (
    CompilerRepairPolicy,
)
from active_skill_system.domain.compiler_types import (
    CompilerActionType,
    CompilerGapClass,
)


def test_default_policy_constructs() -> None:
    p = CompilerRepairPolicy.default_policy()
    assert isinstance(p, CompilerRepairPolicy)
    assert len(p.mapping) == len(list(CompilerGapClass))


def test_default_mapping_covers_every_gap_class() -> None:
    p = CompilerRepairPolicy.default_policy()
    for gap in CompilerGapClass:
        assert p.covers(gap), f"default policy must cover {gap!r}"


def test_default_mapping_for_missing_transform() -> None:
    p = CompilerRepairPolicy.default_policy()
    assert p.action_for(CompilerGapClass.MISSING_TRANSFORM) is CompilerActionType.APPLY_TRANSFORM


def test_default_mapping_for_transform_regression() -> None:
    p = CompilerRepairPolicy.default_policy()
    assert p.action_for(CompilerGapClass.TRANSFORM_REGRESSION) is CompilerActionType.PICK_ALTERNATIVE


def test_default_mapping_for_loop_carried_dep() -> None:
    p = CompilerRepairPolicy.default_policy()
    assert p.action_for(CompilerGapClass.LOOP_CARRIED_DEP) is CompilerActionType.PICK_ALTERNATIVE


def test_default_mapping_for_register_spill() -> None:
    p = CompilerRepairPolicy.default_policy()
    assert p.action_for(CompilerGapClass.REGISTER_SPILL) is CompilerActionType.PICK_ALTERNATIVE


def test_default_mapping_for_perf_regression() -> None:
    p = CompilerRepairPolicy.default_policy()
    # PERF_REGRESSION in the default policy is PICK_ALTERNATIVE (skip this
    # candidate). LOWERING_REPLAN is reserved as a user-facing escape hatch.
    assert p.action_for(CompilerGapClass.PERF_REGRESSION) is CompilerActionType.PICK_ALTERNATIVE


def test_default_mapping_for_transform_regression() -> None:
    p = CompilerRepairPolicy.default_policy()
    # TRANSFORM_REGRESSION is also PICK_ALTERNATIVE in the default policy
    # (skip this candidate and try the next one).
    assert p.action_for(CompilerGapClass.TRANSFORM_REGRESSION) is CompilerActionType.PICK_ALTERNATIVE


def test_default_policy_never_routes_to_lowering_replan() -> None:
    p = CompilerRepairPolicy.default_policy()
    # The bounded candidate loop cannot replan the lowering strategy;
    # routing any default gap class to LOWERING_REPLAN would mean "stop now"
    # for every gap — defeating the loop. LOWERING_REPLAN stays user-only.
    for gap in CompilerGapClass:
        assert p.action_for(gap) is not CompilerActionType.LOWERING_REPLAN


def test_unknown_gap_returns_lowering_replan_fallback() -> None:
    # Construct a policy that covers a single gap; action_for on an uncovered gap falls back.
    p = CompilerRepairPolicy(mapping={CompilerGapClass.MISSING_TRANSFORM: CompilerActionType.APPLY_TRANSFORM})
    assert p.action_for(CompilerGapClass.PERF_REGRESSION) is CompilerActionType.LOWERING_REPLAN


def test_empty_mapping_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        CompilerRepairPolicy(mapping={})


def test_non_dict_mapping_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        CompilerRepairPolicy(mapping=[])  # type: ignore[arg-type]


def test_non_gap_class_key_rejected() -> None:
    with pytest.raises(ValueError, match="CompilerGapClass"):
        CompilerRepairPolicy(mapping={"not_a_gap": CompilerActionType.APPLY_TRANSFORM})  # type: ignore[dict-item]


def test_non_action_value_rejected() -> None:
    with pytest.raises(ValueError, match="CompilerActionType"):
        CompilerRepairPolicy(mapping={CompilerGapClass.MISSING_TRANSFORM: "apply"})  # type: ignore[dict-item]


def test_policy_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    p = CompilerRepairPolicy.default_policy()
    with pytest.raises((FrozenInstanceError, AttributeError)):
        p.mapping = {}  # type: ignore[misc]


def test_covers_returns_false_for_missing_key() -> None:
    p = CompilerRepairPolicy(mapping={CompilerGapClass.MISSING_TRANSFORM: CompilerActionType.APPLY_TRANSFORM})
    assert p.covers(CompilerGapClass.MISSING_TRANSFORM) is True
    assert p.covers(CompilerGapClass.PERF_REGRESSION) is False


def test_module_infra_free() -> None:
    import importlib
    from pathlib import Path

    mod = importlib.import_module("active_skill_system.application.use_cases.compiler_repair_policy")
    src = Path(mod.__file__).read_text()
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"compiler_repair_policy.py must not contain '{forbidden}' (R002)"


def test_separate_from_reasoning_repair_policy() -> None:
    """CompilerRepairPolicy must not import or depend on RepairPolicy."""
    import importlib
    from pathlib import Path

    mod = importlib.import_module("active_skill_system.application.use_cases.compiler_repair_policy")
    src = Path(mod.__file__).read_text()
    assert "from active_skill_system.application.use_cases.repair_policy" not in src
    assert "import repair_policy" not in src
