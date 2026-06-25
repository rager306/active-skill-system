"""Unit tests for Evolvable trait components (M015 S01)."""

from __future__ import annotations

import pytest

from active_skill_system.domain.evolvable import (
    FitnessSignal,
    MutationSpace,
)

# ── FitnessSignal ────────────────────────────────────────────────────────


def test_fitness_signal_constructs() -> None:
    f = FitnessSignal(quality=0.85, cost=0.5, latency=120.0)
    assert f.quality == 0.85
    assert f.regression is False


def test_fitness_signal_with_regression() -> None:
    f = FitnessSignal(quality=0.9, cost=0.3, latency=50.0, regression=True)
    assert f.regression is True


def test_fitness_rejects_quality_out_of_range() -> None:
    with pytest.raises(ValueError, match="quality"):
        FitnessSignal(quality=1.5, cost=1.0, latency=100.0)
    with pytest.raises(ValueError, match="quality"):
        FitnessSignal(quality=-0.1, cost=1.0, latency=100.0)


def test_fitness_rejects_negative_cost() -> None:
    with pytest.raises(ValueError, match="cost"):
        FitnessSignal(quality=0.5, cost=-1.0, latency=100.0)


def test_fitness_rejects_zero_latency() -> None:
    with pytest.raises(ValueError, match="latency"):
        FitnessSignal(quality=0.5, cost=1.0, latency=0.0)


def test_fitness_better_than_higher_quality() -> None:
    a = FitnessSignal(quality=0.9, cost=1.0, latency=100.0)
    b = FitnessSignal(quality=0.8, cost=0.5, latency=50.0)
    assert a.better_than(b) is True
    assert b.better_than(a) is False


def test_fitness_better_than_same_quality_lower_cost() -> None:
    a = FitnessSignal(quality=0.8, cost=0.3, latency=100.0)
    b = FitnessSignal(quality=0.8, cost=0.5, latency=50.0)
    assert a.better_than(b) is True


def test_fitness_regression_never_better() -> None:
    a = FitnessSignal(quality=0.99, cost=0.01, latency=1.0, regression=True)
    b = FitnessSignal(quality=0.5, cost=10.0, latency=1000.0)
    assert a.better_than(b) is False


def test_fitness_non_regression_better_than_regression() -> None:
    a = FitnessSignal(quality=0.5, cost=10.0, latency=1000.0)
    b = FitnessSignal(quality=0.99, cost=0.01, latency=1.0, regression=True)
    assert a.better_than(b) is True


# ── MutationSpace ────────────────────────────────────────────────────────


def test_mutation_space_constructs() -> None:
    m = MutationSpace(description="rephrase template", mutate_fn_name="rephrase")
    assert m.description == "rephrase template"
    assert m.mutate_fn_name == "rephrase"


def test_mutation_space_rejects_empty_description() -> None:
    with pytest.raises(ValueError, match="description"):
        MutationSpace(description="", mutate_fn_name="x")


def test_mutation_space_rejects_empty_fn_name() -> None:
    with pytest.raises(ValueError, match="mutate_fn_name"):
        MutationSpace(description="x", mutate_fn_name="")


# ── R002: domain infra-free ─────────────────────────────────────────────


def test_evolvable_module_infra_free() -> None:
    import importlib
    from pathlib import Path

    mod = importlib.import_module("active_skill_system.domain.evolvable")
    src = Path(mod.__file__).read_text()
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"evolvable.py must not contain '{forbidden}' (R002)"
