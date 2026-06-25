"""L2 Application — Evolvable adapters (M015 S02).

Wraps ModelGenome (M011) and PromptGenome (M012) to conform to the
Evolvable Protocol (D004). These adapters bridge the concrete genome types
to the generic EvolutionEngine (S03) without modifying the domain types.

Pure application. Depends on domain only (R002).
"""

from __future__ import annotations

from typing import Any

from active_skill_system.domain.evolvable import (
    FitnessSignal,
    MutationSpace,
)
from active_skill_system.domain.model_genome import ModelGenome
from active_skill_system.domain.prompt_genome import PromptGenome


class ModelGenomeEvolvable:
    """Adapts ModelGenome to the Evolvable Protocol.

    Mutation strategies: adjust cost profile, swap capabilities.
    Evaluation: measures quality (dataset success-rate), cost (genome cost),
    latency (placeholder — real measurement requires runtime).
    """

    @property
    def mutation_space(self) -> MutationSpace:
        return MutationSpace(
            description="adjust cost profile or swap capabilities",
            mutate_fn_name="adjust_model",
        )

    def mutate(self, genome: Any) -> Any:
        """Produce a variant ModelGenome with slightly adjusted cost."""
        if not isinstance(genome, ModelGenome):
            raise TypeError(f"Expected ModelGenome, got {type(genome).__name__}")
        # Simple mutation: reduce cost by 10% (cheaper variant).
        new_cost_in = genome.cost_input_per_1m * 0.9
        new_cost_out = genome.cost_output_per_1m * 0.9
        return ModelGenome(
            id=f"{genome.id}-mut",
            capabilities=genome.capabilities,
            context_window=genome.context_window,
            cost_input_per_1m=new_cost_in,
            cost_output_per_1m=new_cost_out,
            provider_id=genome.provider_id,
        )

    def evaluate(self, genome: Any, dataset: Any) -> FitnessSignal:
        """Evaluate a ModelGenome against a dataset.

        ``dataset`` is expected to be a dict with:
          - ``success_rate``: float [0, 1] — fraction of successful runs.
          - ``avg_latency_ms``: float > 0 — average latency.
        """
        if not isinstance(genome, ModelGenome):
            raise TypeError(f"Expected ModelGenome, got {type(genome).__name__}")
        ds = dataset if isinstance(dataset, dict) else {}
        quality = float(ds.get("success_rate", 0.5))
        latency = float(ds.get("avg_latency_ms", 100.0))
        cost = genome.cost_input_per_1m + genome.cost_output_per_1m
        return FitnessSignal(quality=quality, cost=cost, latency=latency)


class PromptGenomeEvolvable:
    """Adapts PromptGenome to the Evolvable Protocol.

    Mutation strategies: rephrase template, add/remove slots.
    Evaluation: measures quality (parse-success-rate from dataset).
    """

    @property
    def mutation_space(self) -> MutationSpace:
        return MutationSpace(
            description="rephrase template or adjust slots",
            mutate_fn_name="rephrase",
        )

    def mutate(self, genome: Any) -> Any:
        """Produce a variant PromptGenome with a slightly modified template."""
        if not isinstance(genome, PromptGenome):
            raise TypeError(f"Expected PromptGenome, got {type(genome).__name__}")
        # Simple mutation: append " Be concise." to the template.
        new_template = genome.template.rstrip() + " Be concise."
        return PromptGenome(
            id=f"{genome.id}-mut",
            template=new_template,
            slots=genome.slots,
            version=genome.version + 1,
            invariants=genome.invariants,
        )

    def evaluate(self, genome: Any, dataset: Any) -> FitnessSignal:
        """Evaluate a PromptGenome against a dataset.

        ``dataset`` is expected to be a dict with:
          - ``parse_success_rate``: float [0, 1].
          - ``avg_latency_ms``: float > 0.
          - ``avg_cost``: float >= 0.
        """
        if not isinstance(genome, PromptGenome):
            raise TypeError(f"Expected PromptGenome, got {type(genome).__name__}")
        ds = dataset if isinstance(dataset, dict) else {}
        quality = float(ds.get("parse_success_rate", 0.5))
        latency = float(ds.get("avg_latency_ms", 100.0))
        cost = float(ds.get("avg_cost", 0.5))
        return FitnessSignal(quality=quality, cost=cost, latency=latency)
