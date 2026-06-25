"""Unit tests for EvolutionEngine (M015 S03, M017 S02).

Covers the generic engine operating over three concrete Evolvable cases:
  - ModelGenomeEvolvable (M011)
  - PromptGenomeEvolvable (M012)
  - TransformationGenomeEvolvable (M016) - wired via the M017 S01
    production composition helper (the same closure that main() uses).
"""

from __future__ import annotations

from active_skill_system.application.evolution_engine import (
    EvolutionEngine,
    PromotionResult,
)
from active_skill_system.application.evolvable_adapters import (
    ModelGenomeEvolvable,
    PromptGenomeEvolvable,
    TransformationGenomeEvolvable,
)
from active_skill_system.composition import compiler_evolution
from active_skill_system.domain.compiler_types import (
    CompilerMetrics,
    CompilerNodeKind,
    TransformParams,
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
    """Engine operates generically - works with PromptGenomeEvolvable too."""
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


# ── EvolutionEngine with TransformationGenomeEvolvable (M017 S02) ─────────
# Uses the M017 S01 production composition helper to wire the real
# CompilerToolStub invoker into TransformationGenomeEvolvable. Same closure
# that `python -m active_skill_system.composition.compiler_evolution` uses.


def _transformation_evolvable() -> TransformationGenomeEvolvable:
    """Production-wired TransformationGenomeEvolvable from the L4 composition layer."""
    return compiler_evolution._build_transformation_evolvable()


def _baseline_metrics(cycles: int = 1000) -> CompilerMetrics:
    return CompilerMetrics(
        cycles=cycles, reg_pressure=10, spills=2, energy_proxy=1.0, is_valid=True,
    )


def _tile(tile_size: int = 10) -> TransformParams:
    return TransformParams(
        transform_type=CompilerNodeKind.TRANSFORM_TILE,
        params={"tile_size": tile_size},
        legal=True,
    )


def _unroll(factor: int = 4) -> TransformParams:
    return TransformParams(
        transform_type=CompilerNodeKind.TRANSFORM_UNROLL,
        params={"unroll_factor": factor},
        legal=True,
    )


def _fusion(k: int = 2) -> TransformParams:
    return TransformParams(
        transform_type=CompilerNodeKind.TRANSFORM_FUSION,
        params={"fused_loops": k},
        legal=True,
    )


def test_engine_promotes_transformation_via_production_wiring() -> None:
    """Engine + TransformationGenomeEvolvable (production invoker) must promote on the
    first mutating iteration: TILE 10 → 18 → cycles 1000/18 ≈ 55 → quality ≈ 0.945.
    """
    engine = EvolutionEngine()
    candidates = (_tile(tile_size=10), _unroll(factor=4), _fusion(k=2))
    result = engine.run(
        _transformation_evolvable(),
        baseline_genome=candidates,
        dataset={"baseline_metrics": {"cycles": 1000, "reg_pressure": 10, "spills": 2, "energy_proxy": 1.0, "is_valid": True}},
        max_iterations=5,
    )
    assert result.promoted is True
    assert result.candidate_fitness.quality > result.baseline_fitness.quality
    assert 0.90 <= result.candidate_fitness.quality <= 0.95
    assert result.candidate_fitness.regression is False
    assert "promoted at iteration 1" in result.reason


def test_engine_retains_baseline_when_all_candidates_at_caps() -> None:
    """If every candidate is at its mutation cap (TILE 256 / UNROLL 16 / FUSION 4),
    `_try_mutate_candidate` is a no-op → same fitness → no promotion → ratchet holds.
    """
    engine = EvolutionEngine()
    candidates = (_tile(tile_size=256), _unroll(factor=16), _fusion(k=4))
    result = engine.run(
        _transformation_evolvable(),
        baseline_genome=candidates,
        dataset={"baseline_metrics": {"cycles": 1000, "reg_pressure": 10, "spills": 2, "energy_proxy": 1.0, "is_valid": True}},
        max_iterations=3,
    )
    assert result.promoted is False
    assert result.iterations_used == 3
    assert "No improvement" in result.reason
    # Baseline tuple retained verbatim.
    assert result.promoted_genome == candidates


def test_engine_fitness_signal_invariants_after_transformation_promotion() -> None:
    """FitnessSignal invariants (quality ∈ [0, 1], regression is False on a real promotion)."""
    engine = EvolutionEngine()
    candidates = (_tile(tile_size=10),)
    result = engine.run(
        _transformation_evolvable(),
        baseline_genome=candidates,
        dataset={"baseline_metrics": {"cycles": 1000, "reg_pressure": 10, "spills": 2, "energy_proxy": 1.0, "is_valid": True}},
        max_iterations=2,
    )
    assert 0.0 <= result.candidate_fitness.quality <= 1.0
    assert result.candidate_fitness.regression is False
    assert result.candidate_fitness.cost >= 0.0
    assert result.candidate_fitness.latency > 0.0


def test_engine_handles_interchange_only_candidate_gracefully() -> None:
    """INTERCHANGE has no deterministic numeric parameter to bump — mutate returns
    the same candidate; if the FUSION baseline doesn't beat it either, the engine
    iterates without crashing and reports no promotion.
    """
    from active_skill_system.domain.compiler_types import TransformParams

    interchange = TransformParams(
        transform_type=CompilerNodeKind.TRANSFORM_INTERCHANGE,
        params={},
        legal=True,
    )
    # Pair with a TILE candidate that's already at cap so mutate is a no-op.
    candidates = (interchange, _tile(tile_size=256))
    engine = EvolutionEngine()
    result = engine.run(
        _transformation_evolvable(),
        baseline_genome=candidates,
        dataset={"baseline_metrics": {"cycles": 1000, "reg_pressure": 10, "spills": 2, "energy_proxy": 1.0, "is_valid": True}},
        max_iterations=2,
    )
    # INTERCHANGE is at-cap-equivalent (no param to bump), TILE is at cap → no-op mutate.
    assert result.promoted is False
    assert result.iterations_used == 2


def test_engine_promotes_first_candidate_in_tuple_greedily() -> None:
    """Current EvolutionEngine semantics: terminal on FIRST better candidate (greedy).
    The first TILE candidate (tile_size=10) produces a baseline fitness of quality=0.9
    (cycles 1000/10=100); mutation to tile_size=18 yields quality≈0.945 (cycles 1000/18≈55)
    which is strictly better → promoted at iteration 1.
    """
    engine = EvolutionEngine()
    candidates = (_tile(tile_size=10), _unroll(factor=4))
    result = engine.run(
        _transformation_evolvable(),
        baseline_genome=candidates,
        dataset={"baseline_metrics": {"cycles": 1000, "reg_pressure": 10, "spills": 2, "energy_proxy": 1.0, "is_valid": True}},
        max_iterations=5,
    )
    assert result.iterations_used == 1  # greedy: stop at first improvement
    assert result.promoted is True


def test_engine_with_run_evolution_helper_promotes() -> None:
    """End-to-end via the S01 public API `run_evolution()` — same closure that CLI uses."""
    result = compiler_evolution.run_evolution(
        _baseline_metrics(cycles=1000),
        (_tile(tile_size=10), _unroll(factor=4), _fusion(k=2)),
        max_iterations=5,
    )
    assert result.promoted is True
    assert result.candidate_fitness.quality > 0.9
    assert result.candidate_fitness.regression is False


def test_engine_with_run_evolution_helper_retains_when_at_caps() -> None:
    """Same as test_engine_retains_baseline_when_all_candidates_at_caps but via the
    public run_evolution() API — proves the helper does not hide the ratchet.
    """
    result = compiler_evolution.run_evolution(
        _baseline_metrics(cycles=1000),
        (_tile(tile_size=256), _unroll(factor=16), _fusion(k=4)),
        max_iterations=3,
    )
    assert result.promoted is False
    assert result.iterations_used == 3
    assert "No improvement" in result.reason
