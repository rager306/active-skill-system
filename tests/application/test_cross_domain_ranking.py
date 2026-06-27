"""Cross-domain weighted ranking integration tests (M032 S01).

Combines MultiEvolvableEngine (M024) with WeightedFitnessAggregator (M025)
to enable cross-domain weighted ranking. End-to-end pipeline: run multiple
Evolvables, aggregate their FitnessSignals with weights, select best.
"""

from __future__ import annotations

import pytest

from active_skill_system.application.multi_evolution_engine import MultiEvolvableEngine
from active_skill_system.application.weighted_fitness_aggregator import WeightedFitnessAggregator
from active_skill_system.domain.evolvable import FitnessSignal, MutationSpace


class _ScriptedEvolvable:
    """Evolvable that returns a fixed FitnessSignal — no tool calls needed."""

    def __init__(self, quality: float, cost: float = 1.0, regression: bool = False) -> None:
        self._quality = quality
        self._cost = cost
        self._regression = regression

    @property
    def mutation_space(self) -> MutationSpace:
        return MutationSpace(description="scripted", mutate_fn_name="scripted")

    def mutate(self, genome):
        return f"{genome}-mut"

    def evaluate(self, genome, dataset) -> FitnessSignal:
        # If genome ends with "-mut", return scripted quality (better).
        if str(genome).endswith("-mut"):
            return FitnessSignal(quality=self._quality, cost=self._cost, latency=1.0, regression=self._regression)
        # Baseline genome: lower quality so mutation always improves.
        return FitnessSignal(quality=0.0, cost=self._cost, latency=1.0, regression=self._regression)


# ── Single-domain weighted ranking ──────────────────────────────────────


def test_single_domain_weighted_ranking_promotes() -> None:
    """Single Evolvable: EvolutionEngine promotes via mutation, then WeightedFitnessAggregator scores."""
    evolvable = _ScriptedEvolvable(quality=0.9)
    engine = MultiEvolvableEngine()
    result = engine.run(
        evolvables={"compiler": (evolvable, "comp-baseline")},
        datasets={"compiler": {}},
        max_iterations=3,
    )
    assert result.best_name == "compiler"
    # Aggregate the single signal with weight 1.0 — score should be 0.9.
    agg = WeightedFitnessAggregator(weights={"compiler": 1.0})
    fitness = result.best_promoted.candidate_fitness
    aggregated = agg.aggregate({"compiler": fitness})
    assert aggregated.score == pytest.approx(0.9)
    assert aggregated.regression is False


# ── Cross-domain weighted ranking ───────────────────────────────────────


def test_cross_domain_weighted_ranking_picks_best() -> None:
    """2 Evolvables: compiler quality=0.5, SQL quality=0.8, weight compiler=0.4, SQL=0.6.
    Weighted score: 0.5*0.4 + 0.8*0.6 = 0.2 + 0.48 = 0.68.
    """
    engine = MultiEvolvableEngine()
    result = engine.run(
        evolvables={
            "compiler": (_ScriptedEvolvable(quality=0.5), "comp"),
            "sql": (_ScriptedEvolvable(quality=0.8), "sql"),
        },
        datasets={"compiler": {}, "sql": {}},
        max_iterations=3,
    )
    assert result.best_name == "sql"  # highest single quality wins
    agg = WeightedFitnessAggregator(weights={"compiler": 0.4, "sql": 0.6})
    signals = {
        "compiler": result.results["compiler"].candidate_fitness,
        "sql": result.results["sql"].candidate_fitness,
    }
    aggregated = agg.aggregate(signals)
    assert aggregated.score == pytest.approx(0.2 + 0.48)
    assert aggregated.regression is False


def test_cross_domain_weighted_ranking_heavier_weight_overrides_higher_quality() -> None:
    """Compiler quality=0.9, SQL quality=0.5, weight compiler=0.1, SQL=0.9.
    SQL wins (0.45 > 0.09).
    """
    engine = MultiEvolvableEngine()
    result = engine.run(
        evolvables={
            "compiler": (_ScriptedEvolvable(quality=0.9), "comp"),
            "sql": (_ScriptedEvolvable(quality=0.5), "sql"),
        },
        datasets={"compiler": {}, "sql": {}},
        max_iterations=3,
    )
    # MultiEvolvableEngine picks by raw quality — compiler wins (0.9 > 0.5).
    assert result.best_name == "compiler"
    # But WeightedFitnessAggregator with sql=0.9 weight: SQL wins.
    agg = WeightedFitnessAggregator(weights={"compiler": 0.1, "sql": 0.9})
    signals = {
        "compiler": result.results["compiler"].candidate_fitness,
        "sql": result.results["sql"].candidate_fitness,
    }
    aggregated = agg.aggregate(signals)
    # 0.9*0.1 + 0.5*0.9 = 0.09 + 0.45 = 0.54
    assert aggregated.score == pytest.approx(0.54)


# ── Regression flag propagation through weighted ranking ────────────────


def test_weighted_ranking_regression_propagates_from_any_signal() -> None:
    """If any contributing signal has regression=True, aggregate.regression is True."""
    # Manually construct signals with explicit regression flags.
    agg = WeightedFitnessAggregator(weights={"good": 0.5, "bad": 0.5})
    signals = {
        "good": FitnessSignal(quality=0.9, cost=1.0, latency=1.0, regression=False),
        "bad": FitnessSignal(quality=0.5, cost=1.0, latency=1.0, regression=True),
    }
    aggregated = agg.aggregate(signals)
    assert aggregated.regression is True
    assert "BLOCKED" in aggregated.reason


# ── End-to-end pipeline ────────────────────────────────────────────────


def test_end_to_end_pipeline_promotes_and_aggregates() -> None:
    """Full pipeline: MultiEvolvableEngine → WeightedFitnessAggregator."""
    engine = MultiEvolvableEngine()
    multi_result = engine.run(
        evolvables={
            "compiler": (_ScriptedEvolvable(quality=0.7), "comp"),
            "sql": (_ScriptedEvolvable(quality=0.6), "sql"),
            "storage": (_ScriptedEvolvable(quality=0.5), "stor"),
        },
        datasets={"compiler": {}, "sql": {}, "storage": {}},
        max_iterations=3,
    )
    # All 3 promote; MultiEvolvableEngine picks the highest single quality.
    assert multi_result.best_name == "compiler"
    # WeightedFitnessAggregator with equal weights sums all 3 contributions.
    agg = WeightedFitnessAggregator(weights={"compiler": 1.0/3, "sql": 1.0/3, "storage": 1.0/3})
    signals = {name: multi_result.results[name].candidate_fitness for name in ["compiler", "sql", "storage"]}
    aggregated = agg.aggregate(signals)
    # Sum of (quality * 1/3) = (0.7 + 0.6 + 0.5) / 3 = 0.6
    assert aggregated.score == pytest.approx(0.6, abs=1e-9)
    assert aggregated.regression is False
    assert "3 axis/axes" in aggregated.reason


def test_aggregator_rejects_unknown_signals() -> None:
    """WeightedFitnessAggregator ignores signals not in the weight vector."""
    agg = WeightedFitnessAggregator(weights={"compiler": 1.0})
    signals = {
        "compiler": FitnessSignal(quality=0.5, cost=1.0, latency=1.0),
        "unknown": FitnessSignal(quality=1.0, cost=1.0, latency=1.0),  # ignored
    }
    aggregated = agg.aggregate(signals)
    assert aggregated.score == pytest.approx(0.5)


def test_aggregator_score_uses_candidate_fitness_quality() -> None:
    """Best candidate's candidate_fitness.quality is the primary signal."""
    engine = MultiEvolvableEngine()
    result = engine.run(
        evolvables={"a": (_ScriptedEvolvable(quality=0.5), "a")},
        datasets={"a": {}},
        max_iterations=3,
    )
    # The candidate_fitness.quality should be 0.5.
    assert result.best_promoted.candidate_fitness.quality == pytest.approx(0.5)
    agg = WeightedFitnessAggregator(weights={"a": 1.0})
    aggregated = agg.aggregate({"a": result.best_promoted.candidate_fitness})
    assert aggregated.score == pytest.approx(0.5)
