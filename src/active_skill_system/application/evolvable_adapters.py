"""L2 Application — Evolvable adapters (M015 S02, M016 S03).

Wraps ModelGenome (M011) and PromptGenome (M012) and TransformationGenome
(M016) to conform to the Evolvable Protocol (D004). These adapters bridge
the concrete genome types to the generic EvolutionEngine (S03) without
modifying the domain types.

Pure application. Depends on domain only (R002).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from active_skill_system.domain.compiler_types import (
    CompilerMetrics,
    CompilerNodeKind,
    TransformParams,
)
from active_skill_system.domain.evolvable import (
    Evolvable,
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


# ── TransformationGenomeEvolvable (M016 S03) ──────────────────────────────


# Deterministic mutation caps. Exposed as module constants so tests can
# reference them rather than hardcoding the same numbers.
_TILE_SIZE_MAX: int = 256
_TILE_SIZE_BUMP: int = 8
_UNROLL_FACTOR_MAX: int = 16
_FUSED_LOOPS_MAX: int = 4


def _metrics_to_dict(m: CompilerMetrics) -> dict:
    return {
        "cycles": m.cycles,
        "reg_pressure": m.reg_pressure,
        "spills": m.spills,
        "energy_proxy": m.energy_proxy,
        "is_valid": m.is_valid,
    }


def _parse_metrics(payload: str) -> CompilerMetrics | None:
    try:
        d = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    try:
        return CompilerMetrics(
            cycles=int(d["cycles"]),
            reg_pressure=int(d["reg_pressure"]),
            spills=int(d["spills"]),
            energy_proxy=float(d["energy_proxy"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except (KeyError, TypeError, ValueError):
        return None


class TransformationGenomeEvolvable(Evolvable):
    """Adapts a tuple of :class:`TransformParams` candidates to the Evolvable Protocol.

    The genome is a tuple of candidates (the loop driver tries them in order).
    Mutation applies the first applicable strategy:

      - TILE candidate: bump ``tile_size`` by +8 (cap 256).
      - UNROLL candidate: double ``unroll_factor`` (cap 16).
      - FUSION candidate: increment ``fused_loops`` by +1 (cap 4).
      - INTERCHANGE candidate: no deterministic numeric parameter to tweak,
        so mutate falls back to bumping the TILE candidate if present.

    Evaluation runs each candidate through a CompilerToolStub (or any
    ToolPort-compatible tool resolved via the injected ``invoker`` callable),
    picks the candidate with the best cycles-reduction ratio vs the dataset's
    baseline metrics, and returns a FitnessSignal:

      - quality: best reduction ratio in [0, 1] (0.0 if nothing improves).
      - cost: number of candidates tried.
      - latency: 1.0 ms flat (deterministic; real measurement deferred).
      - regression: True iff no candidate strictly improves the baseline.

    The ``invoker`` is injectable so tests can use a fake tool without
    depending on the L3 adapter layer. Production wiring lives in the
    composition layer (L4) — see ``src/active_skill_system/composition/``,
    which injects the real ``CompilerToolStub`` invoker at composition time.
    The L2 module itself never imports the L3 adapter directly (R007).
    """

    def __init__(
        self,
        invoker: Callable[[dict[str, Any]], tuple[bool, str]],
    ) -> None:
        # invoker(args) -> (success: bool, text: str). Required: production
        # wiring is composition-layer responsibility, not a default here.
        if invoker is None:
            raise ValueError(
                "TransformationGenomeEvolvable requires an invoker; "
                "wire it in the composition layer (see CompilerToolStub)."
            )
        self._invoker = invoker

    @property
    def mutation_space(self) -> MutationSpace:
        return MutationSpace(
            description=(
                "bump TILE tile_size by +8 (cap 256); "
                "double UNROLL factor (cap 16); "
                "increment FUSION fused_loops by +1 (cap 4)"
            ),
            mutate_fn_name="bump_transform_params",
        )

    def mutate(self, genome: Any) -> Any:
        """Produce a variant genome with one bumped parameter.

        Picks the first candidate whose kind has a mutable numeric parameter
        and applies the appropriate bump. Candidates whose kind is not
        mutable (INTERCHANGE) are passed through unchanged.
        """
        if not isinstance(genome, tuple):
            raise TypeError(f"Expected tuple of TransformParams, got {type(genome).__name__}")
        if not all(isinstance(c, TransformParams) for c in genome):
            raise TypeError("Every genome element must be a TransformParams")
        if not genome:
            return genome

        new_candidates: list[TransformParams] = []
        mutated = False
        for cand in genome:
            if mutated:
                new_candidates.append(cand)
                continue
            mutated_cand = _try_mutate_candidate(cand)
            if mutated_cand is cand:
                # No applicable mutation for this kind — try next candidate.
                new_candidates.append(cand)
            else:
                new_candidates.append(mutated_cand)
                mutated = True
        if not mutated:
            # No candidate had a mutable numeric parameter — return a no-op copy
            # so the caller still sees "a variant".
            return tuple(new_candidates)
        return tuple(new_candidates)

    def evaluate(self, genome: Any, dataset: Any) -> FitnessSignal:
        """Evaluate a transformation genome against a dataset.

        ``dataset`` is a dict with:
          - ``baseline_metrics``: dict matching CompilerMetrics fields.
          - (optional) ``max_candidates``: int (default len(genome)).

        Returns a :class:`FitnessSignal` whose quality is the best cycles
        reduction ratio across candidates (0.0 if none improve).
        """
        if not isinstance(genome, tuple):
            raise TypeError(f"Expected tuple of TransformParams, got {type(genome).__name__}")
        if not all(isinstance(c, TransformParams) for c in genome):
            raise TypeError("Every genome element must be a TransformParams")
        ds = dataset if isinstance(dataset, dict) else {}
        baseline_raw = ds.get("baseline_metrics", {})
        if not isinstance(baseline_raw, dict):
            baseline_raw = {}
        try:
            baseline = CompilerMetrics(
                cycles=int(baseline_raw.get("cycles", 1)),
                reg_pressure=int(baseline_raw.get("reg_pressure", 0)),
                spills=int(baseline_raw.get("spills", 0)),
                energy_proxy=float(baseline_raw.get("energy_proxy", 0.0)),
                is_valid=bool(baseline_raw.get("is_valid", True)),
            )
        except (TypeError, ValueError):
            baseline = CompilerMetrics(cycles=1, reg_pressure=0, spills=0, energy_proxy=0.0)

        max_candidates = int(ds.get("max_candidates", len(genome)))
        candidates_to_try = genome[:max_candidates]

        best_reduction = 0.0
        any_improvement = False
        tried = 0
        for cand in candidates_to_try:
            tried += 1
            args = {
                "transform_type": cand.transform_type.value,
                "params": {**cand.params, "legal": cand.legal},
                "baseline": _metrics_to_dict(baseline),
            }
            success, text = self._invoker(args)
            if not success:
                continue
            new_metrics = _parse_metrics(text)
            if new_metrics is None:
                continue
            if new_metrics.better_than(baseline):
                any_improvement = True
                if baseline.cycles > 0:
                    reduction = (baseline.cycles - new_metrics.cycles) / baseline.cycles
                    if reduction > best_reduction:
                        best_reduction = reduction

        # Clamp to [0.0, 1.0] just in case of edge inputs.
        quality = max(0.0, min(1.0, best_reduction))
        cost = float(tried)
        latency = 1.0  # deterministic placeholder
        regression = not any_improvement
        return FitnessSignal(
            quality=quality, cost=cost, latency=latency, regression=regression,
        )


def _try_mutate_candidate(cand: TransformParams) -> TransformParams:
    """Apply the first applicable numeric bump to a candidate.

    Returns the same TransformParams unchanged if no numeric parameter applies.
    """
    params = dict(cand.params)
    kind = cand.transform_type
    if kind is CompilerNodeKind.TRANSFORM_TILE:
        current = int(params.get("tile_size", 32))
        new_size = min(_TILE_SIZE_MAX, current + _TILE_SIZE_BUMP)
        if new_size == current:
            return cand
        params["tile_size"] = new_size
        return TransformParams(transform_type=kind, params=params, legal=cand.legal)
    if kind is CompilerNodeKind.TRANSFORM_UNROLL:
        current = int(params.get("unroll_factor", 2))
        new_factor = min(_UNROLL_FACTOR_MAX, current * 2)
        if new_factor == current:
            return cand
        params["unroll_factor"] = new_factor
        return TransformParams(transform_type=kind, params=params, legal=cand.legal)
    if kind is CompilerNodeKind.TRANSFORM_FUSION:
        current = int(params.get("fused_loops", 2))
        new_k = min(_FUSED_LOOPS_MAX, current + 1)
        if new_k == current:
            return cand
        params["fused_loops"] = new_k
        return TransformParams(transform_type=kind, params=params, legal=cand.legal)
    # INTERCHANGE (or any non-mutable kind): no deterministic numeric bump.
    return cand
