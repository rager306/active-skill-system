"""Conformance tests for ModelGenome + PromptGenome Evolvable (M015 S02)."""

from __future__ import annotations

from active_skill_system.application.evolvable_adapters import (
    ModelGenomeEvolvable,
    PromptGenomeEvolvable,
)
from active_skill_system.domain.evolvable import Evolvable, FitnessSignal
from active_skill_system.domain.model_genome import ModelCapability, ModelGenome
from active_skill_system.domain.prompt_genome import PromptGenome, PromptSlot


def _model_genome() -> ModelGenome:
    return ModelGenome(
        id="m3",
        capabilities=frozenset({ModelCapability.VISION, ModelCapability.THINKING}),
        context_window=1_000_000,
        cost_input_per_1m=1.0,
        cost_output_per_1m=2.0,
        provider_id="router",
    )


def _prompt_genome() -> PromptGenome:
    return PromptGenome(
        id="parse",
        template="Extract JSON from {goal}",
        slots=(PromptSlot(name="goal"),),
    )


# ── Evolvable conformance ────────────────────────────────────────────────


def test_model_genome_evolvable_is_evolvable() -> None:
    assert isinstance(ModelGenomeEvolvable(), Evolvable)


def test_prompt_genome_evolvable_is_evolvable() -> None:
    assert isinstance(PromptGenomeEvolvable(), Evolvable)


# ── ModelGenomeEvolvable ─────────────────────────────────────────────────


def test_model_mutation_space_non_empty() -> None:
    ms = ModelGenomeEvolvable().mutation_space
    assert ms.description
    assert ms.mutate_fn_name


def test_model_mutate_produces_different_genome() -> None:
    original = _model_genome()
    mutated = ModelGenomeEvolvable().mutate(original)
    assert mutated.id != original.id
    assert mutated.cost_input_per_1m < original.cost_input_per_1m


def test_model_evaluate_returns_fitness_signal() -> None:
    result = ModelGenomeEvolvable().evaluate(
        _model_genome(), {"success_rate": 0.85, "avg_latency_ms": 200.0}
    )
    assert isinstance(result, FitnessSignal)
    assert result.quality == 0.85


# ── PromptGenomeEvolvable ────────────────────────────────────────────────


def test_prompt_mutation_space_non_empty() -> None:
    ms = PromptGenomeEvolvable().mutation_space
    assert ms.description
    assert ms.mutate_fn_name


def test_prompt_mutate_produces_different_genome() -> None:
    original = _prompt_genome()
    mutated = PromptGenomeEvolvable().mutate(original)
    assert mutated.template != original.template
    assert mutated.version > original.version


def test_prompt_evaluate_returns_fitness_signal() -> None:
    result = PromptGenomeEvolvable().evaluate(
        _prompt_genome(),
        {"parse_success_rate": 0.9, "avg_latency_ms": 50.0, "avg_cost": 0.3},
    )
    assert isinstance(result, FitnessSignal)
    assert result.quality == 0.9
