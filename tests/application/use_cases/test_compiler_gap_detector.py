"""Unit tests for CompilerGapDetector (M016 S03 T01)."""

from __future__ import annotations

from active_skill_system.application.use_cases.compiler_gap_detector import (
    NO_GAP,
    SPILLS_REGRESSION_RATIO,
    classify_gap,
    is_improved,
)
from active_skill_system.domain.compiler_types import CompilerGapClass, CompilerMetrics


def _m(cycles: int, spills: int, reg: int = 8, energy: float = 1.0, valid: bool = True) -> CompilerMetrics:
    return CompilerMetrics(cycles=cycles, reg_pressure=reg, spills=spills, energy_proxy=energy, is_valid=valid)


# ── NO_GAP sentinel ───────────────────────────────────────────────────────


def test_no_gap_is_a_string_not_enum_value() -> None:
    # Critical: NO_GAP must NOT collide with a CompilerGapClass value.
    assert NO_GAP not in {g.value for g in CompilerGapClass}
    assert isinstance(NO_GAP, str)


# ── Rule 1: first iteration ───────────────────────────────────────────────


def test_first_iteration_returns_missing_transform() -> None:
    assert classify_gap(None, _m(1000, 4)) is CompilerGapClass.MISSING_TRANSFORM


def test_first_iteration_invalid_schedule_returns_spill() -> None:
    # Rule 2 fires before Rule 1 — invalid schedule is always a spill.
    assert classify_gap(None, _m(1000, 4, valid=False)) is CompilerGapClass.REGISTER_SPILL


# ── Rule 2: invalid schedule ──────────────────────────────────────────────


def test_invalid_current_always_returns_spill() -> None:
    prev = _m(1000, 4)
    curr = _m(500, 0, valid=False)  # would normally be NO_GAP, but invalid.
    assert classify_gap(prev, curr) is CompilerGapClass.REGISTER_SPILL


# ── Rule 3: improvement ───────────────────────────────────────────────────


def test_strictly_better_returns_no_gap() -> None:
    prev = _m(1000, 4)
    curr = _m(500, 2)
    assert classify_gap(prev, curr) == NO_GAP


def test_equal_metrics_returns_missing_transform() -> None:
    prev = _m(1000, 4)
    curr = _m(1000, 4)
    # Equal metrics → not strictly better → fall through to Rule 7.
    assert classify_gap(prev, curr) is CompilerGapClass.MISSING_TRANSFORM


def test_is_improved_helper() -> None:
    assert is_improved(_m(1000, 4), _m(500, 2)) is True
    assert is_improved(_m(1000, 4), _m(500, 4)) is True
    assert is_improved(_m(1000, 4), _m(1000, 4)) is False
    assert is_improved(_m(1000, 4), _m(2000, 4)) is False


# ── Rule 4: both regressed ────────────────────────────────────────────────


def test_cycles_and_spills_regressed_returns_perf_regression() -> None:
    prev = _m(1000, 4)
    curr = _m(1500, 8)
    assert classify_gap(prev, curr) is CompilerGapClass.PERF_REGRESSION


# ── Rule 5: cycles improved, spills worse ─────────────────────────────────


def test_cycles_improved_spills_more_than_doubled_returns_spill() -> None:
    prev = _m(1000, 4)
    curr = _m(500, 10)  # spills went 4 → 10 (> 2x)
    assert classify_gap(prev, curr) is CompilerGapClass.REGISTER_SPILL
    assert SPILLS_REGRESSION_RATIO == 2.0


def test_cycles_improved_spills_zero_to_nonzero_returns_spill() -> None:
    prev = _m(1000, 0)
    curr = _m(500, 1)
    assert classify_gap(prev, curr) is CompilerGapClass.REGISTER_SPILL


def test_cycles_improved_spills_slight_increase_returns_missing() -> None:
    # Spills went 4 → 5 (not > 2x) → tolerable trade-off.
    prev = _m(1000, 4)
    curr = _m(500, 5)
    assert classify_gap(prev, curr) is CompilerGapClass.MISSING_TRANSFORM


# ── Rule 6: cycles regressed, spills improved ─────────────────────────────


def test_cycles_regressed_spills_improved_returns_transform_regression() -> None:
    prev = _m(500, 8)
    curr = _m(800, 2)  # slower but fewer spills
    assert classify_gap(prev, curr) is CompilerGapClass.TRANSFORM_REGRESSION


# ── Rule 7: no meaningful movement ────────────────────────────────────────


def test_no_movement_returns_missing_transform() -> None:
    prev = _m(1000, 4)
    curr = _m(1000, 4)
    assert classify_gap(prev, curr) is CompilerGapClass.MISSING_TRANSFORM


# ── module hygiene ────────────────────────────────────────────────────────


def test_module_infra_free() -> None:
    import importlib
    from pathlib import Path

    mod = importlib.import_module("active_skill_system.application.use_cases.compiler_gap_detector")
    src = Path(mod.__file__).read_text()
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"compiler_gap_detector.py must not contain '{forbidden}' (R002)"


def test_classify_gap_pure_no_side_effects() -> None:
    """Calling classify_gap multiple times must return the same value (pure)."""
    prev = _m(1000, 4)
    curr = _m(500, 2)
    first = classify_gap(prev, curr)
    second = classify_gap(prev, curr)
    third = classify_gap(prev, curr)
    assert first == second == third == NO_GAP
