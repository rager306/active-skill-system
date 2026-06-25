"""Unit tests for EvolutionEngine (M015 S03)."""

from __future__ import annotations

from active_skill_system.application.evolution_engine import (
    EvolutionEngine,
    PromotionResult,
)
from active_skill_system.application.evolvable_adapters import (
    ModelGenomeEvolvable,
    PromptGenomeEvolvable,
)
from active_skill_system.domain.evolvable import FitnessSignal
from active_skill_system.domain.model_genome import ModelCapability, ModelGenome
from active_skill_system.domain.prompt_genome import PromptGenome, PromptSlot


def _model() -> ModelGenome:
    return ModelGenome(
        id="m3",
        capabilities=frozenset({ModelCapability.VISION}),
        context_window=1_000_000,
        cost_input_per_1m=1.0,
        cost_output_per_1m=2.0,
        provider_id="router",
    )


def _prompt() -> PromptGenome:
    return PromptGenome(
        id="parse",
        template="Extract from {goal}",
        slots=(PromptSlot("goal"),),
    )


# ── EvolutionEngine with ModelGenomeEvolvable ────────────────────────────


def test_engine_promotes_cheaper_model() -> None:
    """ModelGenomeEvolvable mutates to lower cost → better_than baseline → promoted."""
    engine = EvolutionEngine()
    result = engine.run(
        ModelGenomeEvolvable(),
        _model(),
        {"success_rate": 0.8, "avg_latency_ms": 100.0},
        max_iterations=3,
    )
    # Mutation reduces cost → candidate cost < baseline → better_than.
    # But quality is same (dataset constant) → better by cost.
    assert isinstance(result, PromotionResult)
    assert result.candidate_fitness.cost < result.baseline_fitness.cost


def test_engine_result_has_reason() -> None:
    engine = EvolutionEngine()
    result = engine.run(
        ModelGenomeEvolvable(),
        _model(),
        {"success_rate": 0.8, "avg_latency_ms": 100.0},
        max_iterations=3,
    )
    assert len(result.reason) > 0


def test_engine_iterations_used() -> None:
    engine = EvolutionEngine()
    result = engine.run(
        ModelGenomeEvolvable(),
        _model(),
        {"success_rate": 0.8, "avg_latency_ms": 100.0},
        max_iterations=5,
    )
    assert 1 <= result.iterations_used <= 5


# ── EvolutionEngine with PromptGenomeEvolvable ───────────────────────────


def test_engine_works_with_prompt_genome() -> None:
    """Engine operates generically — works with PromptGenomeEvolvable too."""
    engine = EvolutionEngine()
    result = engine.run(
        PromptGenomeEvolvable(),
        _prompt(),
        {"parse_success_rate": 0.7, "avg_latency_ms": 50.0, "avg_cost": 0.3},
        max_iterations=3,
    )
    assert isinstance(result, PromotionResult)
    assert isinstance(result.baseline_fitness, FitnessSignal)


# ── Baseline-ratchet: only strictly better promoted ─────────────────────


def test_engine_retains_baseline_when_no_improvement() -> None:
    """If mutation doesn't improve fitness → baseline retained."""

    from active_skill_system.domain.evolvable import FitnessSignal, MutationSpace

    class _NoOpEvolvable:
        """Evolvable that always produces same-fitness candidates (no improvement)."""

        @property
        def mutation_space(self) -> MutationSpace:
            return MutationSpace(description="noop", mutate_fn_name="noop")

        def mutate(self, genome):
            return genome  # same genome → same fitness

        def evaluate(self, genome, dataset) -> FitnessSignal:
            return FitnessSignal(quality=0.5, cost=1.0, latency=100.0)

    engine = EvolutionEngine()
    result = engine.run(
        _NoOpEvolvable(),
        "baseline-genome",
        {},
        max_iterations=3,
    )
    assert result.promoted is False
    assert result.iterations_used == 3
    assert "No improvement" in result.reason


def test_engine_promoted_genome_is_baseline_when_not_promoted() -> None:
    """When not promoted, promoted_genome == baseline_genome."""

    from active_skill_system.domain.evolvable import FitnessSignal, MutationSpace

    class _NoOpEvolvable:
        @property
        def mutation_space(self) -> MutationSpace:
            return MutationSpace(description="noop", mutate_fn_name="noop")

        def mutate(self, genome):
            return genome

        def evaluate(self, genome, dataset) -> FitnessSignal:
            return FitnessSignal(quality=0.5, cost=1.0, latency=100.0)

    engine = EvolutionEngine()
    result = engine.run(_NoOpEvolvable(), "baseline", {}, max_iterations=2)
    assert result.promoted_genome == "baseline"


# ── PromotionResult structure ────────────────────────────────────────────


def test_promotion_result_is_frozen() -> None:
    r = PromotionResult(
        promoted=False,
        promoted_genome="x",
        baseline_fitness=FitnessSignal(quality=0.5, cost=1.0, latency=100.0),
        candidate_fitness=FitnessSignal(quality=0.5, cost=1.0, latency=100.0),
        iterations_used=0,
        reason="test",
    )
    import pytest

    with pytest.raises(AttributeError):
        r.promoted = True  # type: ignore[misc]
