"""Tests for the sandbox verifier (M042 S01 T03)."""

from __future__ import annotations

from pathlib import Path

from active_skill_system.application.use_cases.sandbox_verifier import (
    SandboxFitness,
    verify_candidate,
)

_FULL = Path("tests/fixtures/sandbox/cache_full.py")
_BROKEN = Path("tests/fixtures/sandbox/cache_broken.py")


def test_full_candidate_scores_one():
    fitness = verify_candidate(_FULL)
    assert isinstance(fitness, SandboxFitness)
    assert fitness.structure_ok is True
    assert fitness.invariants_ok is True
    assert fitness.ranking_ok is True
    assert fitness.loc_ok is True
    assert fitness.score == 1.0


def test_broken_candidate_scores_below_one():
    fitness = verify_candidate(_BROKEN)
    assert fitness.score < 1.0
    # The broken fixture has wrong field names → structure fails.
    assert fitness.structure_ok is False
    assert fitness.invariants_ok is False
    assert fitness.ranking_ok is False


def test_full_and_broken_distinguish():
    full = verify_candidate(_FULL)
    broken = verify_candidate(_BROKEN)
    assert full.score > broken.score


def test_missing_file_returns_zero_fitness():
    fitness = verify_candidate("tests/fixtures/sandbox/does_not_exist.py")
    assert fitness.score == 0.0
    assert fitness.structure_ok is False


def test_axes_dict_complete():
    fitness = verify_candidate(_FULL)
    axes = fitness.axes()
    for key in (
        "structure_ok", "invariants_ok", "ranking_ok", "ruff_clean",
        "ty_clean", "pyrefly_clean", "risk_ok", "loc", "loc_ok", "score",
    ):
        assert key in axes, f"missing axis {key}"


def test_fitness_repr_includes_score():
    fitness = verify_candidate(_FULL)
    assert "score=" in repr(fitness)


def test_full_candidate_quality_tools_clean():
    """The full candidate must pass ruff + ty + pyrefly (real tool invocations)."""
    fitness = verify_candidate(_FULL)
    assert fitness.ruff_clean is True
    assert fitness.ty_clean is True
    assert fitness.pyrefly_clean is True
