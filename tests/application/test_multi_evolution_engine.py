"""Tests for MultiEvolvableEngine (M024 S01)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from active_skill_system.application.evolution_engine import (
    EvolutionEngine,
)
from active_skill_system.application.multi_evolution_engine import (
    MultiEvolvableEngine,
    MultiPromotionResult,
)
from active_skill_system.domain.evolvable import (
    FitnessSignal,
    MutationSpace,
)


class _FakeEvolvable:
    """Test evolvable with controlled quality/cost to drive best selection.

    baseline_genome is a string; mutate() returns genome + "-mut".
    evaluate() returns a fixed quality/cost when genome ends with "-mut",
    otherwise a low-quality baseline fitness (so mutation always improves).
    """

    def __init__(self, quality: float, cost: float = 1.0, promote: bool = True) -> None:
        self._quality = quality
        self._cost = cost
        self._promote = promote

    @property
    def mutation_space(self) -> MutationSpace:
        return MutationSpace(description="fake", mutate_fn_name="fake")

    def mutate(self, genome):
        return str(genome) + "-mut"

    def evaluate(self, genome, dataset) -> FitnessSignal:
        if str(genome).endswith("-mut"):
            return FitnessSignal(quality=self._quality, cost=self._cost, latency=1.0, regression=not self._promote)
        # Baseline genome: low quality so the mutation always improves.
        return FitnessSignal(quality=0.0, cost=self._cost, latency=1.0, regression=not self._promote)


# ── MultiPromotionResult structure ────────────────────────────────────────


def test_multi_promotion_result_is_frozen() -> None:
    r = MultiPromotionResult(
        results={},
        best_name=None,
        best_promoted=None,
        reason="test",
    )
    with pytest.raises((AttributeError, Exception)):
        r.best_name = "x"  # type: ignore[misc]


def test_multi_promotion_result_defaults() -> None:
    r = MultiPromotionResult()
    assert r.results == {}
    assert r.best_name is None
    assert r.best_promoted is None
    assert r.reason == ""


# ── MultiEvolvableEngine.run ──────────────────────────────────────────────


def test_run_with_two_evolvables_picks_best_by_quality() -> None:
    """Compiler-like (quality=0.5) vs SQL-like (quality=0.9) — best is SQL."""
    engine = MultiEvolvableEngine()
    result = engine.run(
        evolvables={
            "compiler": (_FakeEvolvable(quality=0.5), "compiler-genome"),
            "sql": (_FakeEvolvable(quality=0.9), "sql-genome"),
        },
        datasets={"compiler": {}, "sql": {}},
        max_iterations=3,
    )
    assert isinstance(result, MultiPromotionResult)
    assert result.best_name == "sql"
    assert result.best_promoted is not None
    assert result.best_promoted.candidate_fitness.quality == 0.9


def test_run_with_two_evolvables_tie_break_by_cost() -> None:
    """Equal quality, different cost — best is the lower-cost one."""
    engine = MultiEvolvableEngine()
    result = engine.run(
        evolvables={
            "a": (_FakeEvolvable(quality=0.5, cost=2.0), "a"),
            "b": (_FakeEvolvable(quality=0.5, cost=1.0), "b"),
        },
        datasets={"a": {}, "b": {}},
        max_iterations=2,
    )
    assert result.best_name == "b"
    assert result.best_promoted.candidate_fitness.cost == 1.0


def test_run_with_single_evolvable_works() -> None:
    engine = MultiEvolvableEngine()
    result = engine.run(
        evolvables={"only": (_FakeEvolvable(quality=0.8), "g")},
        datasets={"only": {}},
        max_iterations=2,
    )
    assert result.best_name == "only"
    assert result.best_promoted.candidate_fitness.quality == 0.8


def test_run_with_empty_evolvables_returns_empty_result() -> None:
    engine = MultiEvolvableEngine()
    result = engine.run(evolvables={}, datasets={}, max_iterations=3)
    assert result.results == {}
    assert result.best_name is None
    assert result.best_promoted is None
    assert "No promotion" in result.reason


def test_run_with_no_promotions_returns_best_none() -> None:
    """When no evolvable promotes, best_promoted is None."""
    engine = MultiEvolvableEngine()
    result = engine.run(
        evolvables={
            "a": (_FakeEvolvable(quality=0.5, promote=False), "a"),
            "b": (_FakeEvolvable(quality=0.9, promote=False), "b"),
        },
        datasets={"a": {}, "b": {}},
        max_iterations=2,
    )
    assert result.best_name is None
    assert result.best_promoted is None
    assert "No promotion" in result.reason


def test_run_reason_mentions_promoted_count() -> None:
    engine = MultiEvolvableEngine()
    result = engine.run(
        evolvables={
            "a": (_FakeEvolvable(quality=0.5, promote=True), "a"),
            "b": (_FakeEvolvable(quality=0.9, promote=False), "b"),
        },
        datasets={"a": {}, "b": {}},
        max_iterations=2,
    )
    assert "1/2 evolvable(s) promoted" in result.reason


def test_run_rejects_non_dict_evolvables() -> None:
    engine = MultiEvolvableEngine()
    with pytest.raises(TypeError, match="evolvables must be a dict"):
        engine.run(evolvables=[("a", (_FakeEvolvable(0.5), "a"))], datasets={}, max_iterations=1)  # type: ignore[arg-type]


def test_run_rejects_zero_max_iterations() -> None:
    engine = MultiEvolvableEngine()
    with pytest.raises(ValueError, match="max_iterations"):
        engine.run(evolvables={}, datasets={}, max_iterations=0)


def test_run_rejects_non_evolvable() -> None:
    engine = MultiEvolvableEngine()
    with pytest.raises(TypeError, match="Evolvable Protocol"):
        engine.run(
            evolvables={"a": ("not an evolvable", "g")},  # type: ignore[arg-type]
            datasets={"a": {}},
            max_iterations=1,
        )


def test_run_rejects_non_tuple_pair() -> None:
    engine = MultiEvolvableEngine()
    with pytest.raises(ValueError, match=r"\(evolvable, baseline_genome\) tuple"):
        engine.run(
            evolvables={"a": "just a string"},  # type: ignore[dict-item]
            datasets={"a": {}},
            max_iterations=1,
        )


def test_run_uses_injected_engine() -> None:
    """Engine injection seam: tests can supply a custom EvolutionEngine."""
    custom = EvolutionEngine()
    engine = MultiEvolvableEngine(engine=custom)
    assert engine._engine is custom


# ── R002 ────────────────────────────────────────────────────────────────


def test_module_infra_free() -> None:
    mod = importlib.import_module("active_skill_system.application.multi_evolution_engine")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"multi_evolution_engine.py must not contain '{forbidden}' (R002)"
