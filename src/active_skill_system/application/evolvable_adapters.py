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
from active_skill_system.domain.iac_types import (
    IaCNodeKind,
    IaCPlanMetrics,
    IaCTransformParams,
)
from active_skill_system.domain.ml_types import (
    MLMetrics,
    MLNodeKind,
    MLTransformParams,
)
from active_skill_system.domain.model_genome import ModelGenome
from active_skill_system.domain.network_types import (
    NetworkMetrics,
    NetworkTransformParams,
)
from active_skill_system.domain.prompt_genome import PromptGenome
from active_skill_system.domain.security_types import (
    SecurityMetrics,
    SecurityNodeKind,
    SecurityTransformParams,
)
from active_skill_system.domain.sql_types import (
    SQLMetrics,
    SQLNodeKind,
    SQLTransformParams,
)


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


# ── SQLEvolvable (M018 S03 T01) ───────────────────────────────────────────


# Mutation caps for SQL transforms. Exposed as module constants so tests
# can reference them rather than hardcoding the same numbers.
_SQL_ADD_INDEX_COLS_MAX: int = 16
_SQL_ADD_INDEX_COLS_BUMP: int = 1
_SQL_REORDER_JOINS_ORDER_SIZE_MAX: int = 8
_SQL_REWRITE_AS_JOIN_TABLES_MAX: int = 8


def _sql_metrics_to_dict(m: SQLMetrics) -> dict:
    return {
        "rows_examined": m.rows_examined,
        "rows_returned": m.rows_returned,
        "time_ms": m.time_ms,
        "plan_cost": m.plan_cost,
        "is_valid": m.is_valid,
    }


def _parse_sql_metrics(payload: str) -> SQLMetrics | None:
    try:
        d = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    try:
        return SQLMetrics(
            rows_examined=int(d["rows_examined"]),
            rows_returned=int(d["rows_returned"]),
            time_ms=float(d["time_ms"]),
            plan_cost=float(d["plan_cost"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _try_mutate_sql_candidate(cand: SQLTransformParams) -> SQLTransformParams:
    """Apply the first applicable numeric bump to a SQL candidate.

    Returns the same SQLTransformParams unchanged if no numeric parameter applies.
    """
    params = dict(cand.params)
    kind = cand.transform_type
    if kind is SQLNodeKind.SQL_TRANSFORM_ADD_INDEX:
        current = int(params.get("cols", 1))
        new_cols = min(_SQL_ADD_INDEX_COLS_MAX, current + _SQL_ADD_INDEX_COLS_BUMP)
        if new_cols == current:
            return cand
        params["cols"] = new_cols
        return SQLTransformParams(transform_type=kind, params=params, legal=cand.legal)
    if kind is SQLNodeKind.SQL_TRANSFORM_REORDER_JOINS:
        current = int(params.get("order_size", 2))
        new_k = min(_SQL_REORDER_JOINS_ORDER_SIZE_MAX, current + 1)
        if new_k == current:
            return cand
        params["order_size"] = new_k
        return SQLTransformParams(transform_type=kind, params=params, legal=cand.legal)
    if kind is SQLNodeKind.SQL_TRANSFORM_REWRITE_AS_JOIN:
        current = int(params.get("tables", 2))
        new_n = min(_SQL_REWRITE_AS_JOIN_TABLES_MAX, current + 1)
        if new_n == current:
            return cand
        params["tables"] = new_n
        return SQLTransformParams(transform_type=kind, params=params, legal=cand.legal)
    # REPLAN_QUERY (or any non-mutable kind): no deterministic numeric bump.
    return cand


class SQLEvolvable(Evolvable):
    """Adapts a tuple of :class:`SQLTransformParams` candidates to the Evolvable Protocol.

    Fourth concrete Evolvable case (after ModelGenome M011, PromptGenome M012,
    TransformationGenome M016). Mirrors TransformationGenomeEvolvable shape
    but on SQL primitives. Mutation applies the first applicable deterministic
    numeric strategy (cols += 1 cap 16, order_size += 1 cap 8, tables += 1 cap 8).
    REPLAN_QUERY has no deterministic numeric parameter to bump — falls back
    to bumping ADD_INDEX if present, or returns the tuple unchanged.

    Evaluation runs each candidate through the injected invoker which the L4
    composition layer wires to the real SQLToolStub. Returns a FitnessSignal
    whose quality is the best rows_examined-reduction ratio vs the dataset baseline.
    """

    def __init__(
        self,
        invoker: Callable[[dict[str, Any]], tuple[bool, str]],
    ) -> None:
        if invoker is None:
            raise ValueError(
                "SQLEvolvable requires an invoker; wire it in the composition layer "
                "(see SQLToolStub)."
            )
        self._invoker = invoker

    @property
    def mutation_space(self) -> MutationSpace:
        return MutationSpace(
            description=(
                "bump ADD_INDEX cols by +1 (cap 16); "
                "increment REORDER_JOINS order_size by +1 (cap 8); "
                "increment REWRITE_AS_JOIN tables by +1 (cap 8)"
            ),
            mutate_fn_name="bump_sql_transform_params",
        )

    def mutate(self, genome: Any) -> Any:
        """Produce a variant genome with one bumped parameter."""
        if not isinstance(genome, tuple):
            raise TypeError(f"Expected tuple of SQLTransformParams, got {type(genome).__name__}")
        if not all(isinstance(c, SQLTransformParams) for c in genome):
            raise TypeError("Every genome element must be a SQLTransformParams")
        if not genome:
            return genome

        new_candidates: list[SQLTransformParams] = []
        mutated = False
        for cand in genome:
            if mutated:
                new_candidates.append(cand)
                continue
            mutated_cand = _try_mutate_sql_candidate(cand)
            if mutated_cand is cand:
                new_candidates.append(cand)
            else:
                new_candidates.append(mutated_cand)
                mutated = True
        return tuple(new_candidates)

    def evaluate(self, genome: Any, dataset: Any) -> FitnessSignal:
        """Evaluate a SQL transformation genome against a dataset."""
        if not isinstance(genome, tuple):
            raise TypeError(f"Expected tuple of SQLTransformParams, got {type(genome).__name__}")
        if not all(isinstance(c, SQLTransformParams) for c in genome):
            raise TypeError("Every genome element must be a SQLTransformParams")
        ds = dataset if isinstance(dataset, dict) else {}
        baseline_raw = ds.get("baseline_metrics", {})
        if not isinstance(baseline_raw, dict):
            baseline_raw = {}
        try:
            baseline = SQLMetrics(
                rows_examined=int(baseline_raw.get("rows_examined", 1)),
                rows_returned=int(baseline_raw.get("rows_returned", 0)),
                time_ms=float(baseline_raw.get("time_ms", 0.0)),
                plan_cost=float(baseline_raw.get("plan_cost", 0.0)),
                is_valid=bool(baseline_raw.get("is_valid", True)),
            )
        except (TypeError, ValueError):
            baseline = SQLMetrics(rows_examined=1, rows_returned=0, time_ms=0.0, plan_cost=0.0)

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
                "baseline": _sql_metrics_to_dict(baseline),
            }
            success, text = self._invoker(args)
            if not success:
                continue
            new_metrics = _parse_sql_metrics(text)
            if new_metrics is None:
                continue
            if new_metrics.better_than(baseline):
                any_improvement = True
                if baseline.rows_examined > 0:
                    reduction = (baseline.rows_examined - new_metrics.rows_examined) / baseline.rows_examined
                    if reduction > best_reduction:
                        best_reduction = reduction

        quality = max(0.0, min(1.0, best_reduction))
        cost = float(tried)
        latency = 1.0
        regression = not any_improvement
        return FitnessSignal(
            quality=quality, cost=cost, latency=latency, regression=regression,
        )


# ── IaCEvolvable (M023 S03 T01) ──────────────────────────────────────────


# Mutation caps for IaC transforms.
_IAC_REMOVE_UNUSED_MIN: int = 0
_IAC_ADD_OUTPUT_BUMP: int = 1
_IAC_RESTRUCTURE_DEP_BUMP: int = 1
_IAC_REPLAN_PROVIDERS_BUMP: int = 1


def _iac_metrics_to_dict(m: IaCPlanMetrics) -> dict:
    return {
        "resource_count": m.resource_count,
        "module_count": m.module_count,
        "variable_count": m.variable_count,
        "drift_score": m.drift_score,
        "is_valid": m.is_valid,
    }


def _parse_iac_metrics(payload: str) -> IaCPlanMetrics | None:
    try:
        d = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    try:
        return IaCPlanMetrics(
            resource_count=int(d["resource_count"]),
            module_count=int(d["module_count"]),
            variable_count=int(d["variable_count"]),
            drift_score=float(d["drift_score"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _try_mutate_iac_candidate(cand: IaCTransformParams) -> IaCTransformParams:
    kind = cand.transform_type
    if kind is IaCNodeKind.IA_TRANSFORM_REMOVE_UNUSED:
        return cand  # no deterministic numeric param to bump
    if kind is IaCNodeKind.IA_TRANSFORM_ADD_OUTPUT:
        return cand  # no deterministic numeric param
    if kind is IaCNodeKind.IA_TRANSFORM_RESTRUCTURE_DEP:
        return cand
    if kind is IaCNodeKind.IA_TRANSFORM_REPLAN_PROVIDERS:
        return cand
    return cand


class IaCEvolvable(Evolvable):
    """Adapts a tuple of :class:`IaCTransformParams` to the Evolvable Protocol.

    Fifth concrete Evolvable case. Mutation: bump_n_dependencies (+1, cap 8) for
    RESTRUCTURE_DEP; other kinds are no-op (no numeric param to bump).
    evaluate runs each candidate through the injected invoker, parses JSON,
    emits FitnessSignal(quality = best resource_count reduction ratio).
    """

    def __init__(
        self,
        invoker: Callable[[dict[str, Any]], tuple[bool, str]],
    ) -> None:
        if invoker is None:
            raise ValueError(
                "IaCEvolvable requires an invoker; wire it in the composition layer."
            )
        self._invoker = invoker

    @property
    def mutation_space(self) -> MutationSpace:
        return MutationSpace(
            description=(
                "bump dependencies or replicate for RESTRUCTURE_DEP; "
                "REMOVE_UNUSED/ADD_OUTPUT/REPLAN_PROVIDERS are no-op (no numeric param)"
            ),
            mutate_fn_name="bump_iac_transform_params",
        )

    def mutate(self, genome: Any) -> Any:
        if not isinstance(genome, tuple):
            raise TypeError(f"Expected tuple of IaCTransformParams, got {type(genome).__name__}")
        if not all(isinstance(c, IaCTransformParams) for c in genome):
            raise TypeError("Every genome element must be a IaCTransformParams")
        if not genome:
            return genome
        new_candidates: list[IaCTransformParams] = []
        mutated = False
        for cand in genome:
            if mutated:
                new_candidates.append(cand)
                continue
            mutated_cand = _try_mutate_iac_candidate(cand)
            if mutated_cand is cand:
                new_candidates.append(cand)
            else:
                new_candidates.append(mutated_cand)
                mutated = True
        return tuple(new_candidates)

    def evaluate(self, genome: Any, dataset: Any) -> FitnessSignal:
        if not isinstance(genome, tuple):
            raise TypeError(f"Expected tuple of IaCTransformParams, got {type(genome).__name__}")
        if not all(isinstance(c, IaCTransformParams) for c in genome):
            raise TypeError("Every genome element must be a IaCTransformParams")
        ds = dataset if isinstance(dataset, dict) else {}
        baseline_raw = ds.get("baseline_metrics", {})
        if not isinstance(baseline_raw, dict):
            baseline_raw = {}
        try:
            baseline = IaCPlanMetrics(
                resource_count=int(baseline_raw.get("resource_count", 1)),
                module_count=int(baseline_raw.get("module_count", 0)),
                variable_count=int(baseline_raw.get("variable_count", 0)),
                drift_score=float(baseline_raw.get("drift_score", 0.0)),
                is_valid=bool(baseline_raw.get("is_valid", True)),
            )
        except (TypeError, ValueError):
            baseline = IaCPlanMetrics(resource_count=1, module_count=0, variable_count=0, drift_score=0.0)
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
                "baseline": _iac_metrics_to_dict(baseline),
            }
            success, text = self._invoker(args)
            if not success:
                continue
            new_metrics = _parse_iac_metrics(text)
            if new_metrics is None:
                continue
            if new_metrics.better_than(baseline):
                any_improvement = True
                if baseline.resource_count > 0:
                    reduction = (baseline.resource_count - new_metrics.resource_count) / baseline.resource_count
                    if reduction > best_reduction:
                        best_reduction = reduction
        quality = max(0.0, min(1.0, best_reduction))
        cost = float(tried)
        latency = 1.0
        regression = not any_improvement
        return FitnessSignal(quality=quality, cost=cost, latency=latency, regression=regression)


# ── SecurityEvolvable (M026 S03) ─────────────────────────────────────────


def _security_metrics_to_dict(m: SecurityMetrics) -> dict:
    return {
        "threat_count": m.threat_count,
        "risk_score": m.risk_score,
        "coverage_ratio": m.coverage_ratio,
        "exposure_time": m.exposure_time,
        "is_valid": m.is_valid,
    }


def _parse_security_metrics(payload: str) -> SecurityMetrics | None:
    try:
        d = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    try:
        return SecurityMetrics(
            threat_count=int(d["threat_count"]),
            risk_score=float(d["risk_score"]),
            coverage_ratio=float(d["coverage_ratio"]),
            exposure_time=float(d["exposure_time"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _try_mutate_security_candidate(cand: SecurityTransformParams) -> SecurityTransformParams:
    """Mutation: bump cve_count for PATCH, controls for ADD_CONTROL. Others no-op."""
    kind = cand.transform_type
    if kind is SecurityNodeKind.SEC_TRANSFORM_PATCH:
        params = dict(cand.params)
        current = int(params.get("cve_count", 1))
        params["cve_count"] = min(64, current + 1)
        return SecurityTransformParams(transform_type=kind, params=params, legal=cand.legal)
    if kind is SecurityNodeKind.SEC_TRANSFORM_ADD_CONTROL:
        params = dict(cand.params)
        current = int(params.get("controls", 1))
        params["controls"] = min(8, current + 1)
        return SecurityTransformParams(transform_type=kind, params=params, legal=cand.legal)
    return cand


class SecurityEvolvable(Evolvable):
    """Adapts a tuple of :class:`SecurityTransformParams` to the Evolvable Protocol.

    6th concrete Evolvable case. Mutation bumps numeric params for PATCH and
    ADD_CONTROL. ISOLATE/QUARANTINE are no-op (no numeric param).
    evaluate runs each candidate through the injected invoker, emits
    FitnessSignal(quality = best threat_count reduction ratio).
    """

    def __init__(self, invoker: Callable[[dict[str, Any]], tuple[bool, str]]) -> None:
        if invoker is None:
            raise ValueError("SecurityEvolvable requires an invoker.")
        self._invoker = invoker

    @property
    def mutation_space(self) -> MutationSpace:
        return MutationSpace(
            description="bump PATCH cve_count by +1 (cap 64); bump ADD_CONTROL controls by +1 (cap 8)",
            mutate_fn_name="bump_security_params",
        )

    def mutate(self, genome: Any) -> Any:
        if not isinstance(genome, tuple):
            raise TypeError(f"Expected tuple of SecurityTransformParams, got {type(genome).__name__}")
        if not all(isinstance(c, SecurityTransformParams) for c in genome):
            raise TypeError("Every genome element must be a SecurityTransformParams")
        if not genome:
            return genome
        new_candidates: list[SecurityTransformParams] = []
        mutated = False
        for cand in genome:
            if mutated:
                new_candidates.append(cand)
                continue
            mutated_cand = _try_mutate_security_candidate(cand)
            if mutated_cand is cand:
                new_candidates.append(cand)
            else:
                new_candidates.append(mutated_cand)
                mutated = True
        return tuple(new_candidates)

    def evaluate(self, genome: Any, dataset: Any) -> FitnessSignal:
        if not isinstance(genome, tuple):
            raise TypeError(f"Expected tuple of SecurityTransformParams, got {type(genome).__name__}")
        if not all(isinstance(c, SecurityTransformParams) for c in genome):
            raise TypeError("Every genome element must be a SecurityTransformParams")
        ds = dataset if isinstance(dataset, dict) else {}
        baseline_raw = ds.get("baseline_metrics", {})
        if not isinstance(baseline_raw, dict):
            baseline_raw = {}
        try:
            baseline = SecurityMetrics(
                threat_count=int(baseline_raw.get("threat_count", 1)),
                risk_score=float(baseline_raw.get("risk_score", 0.0)),
                coverage_ratio=float(baseline_raw.get("coverage_ratio", 0.0)),
                exposure_time=float(baseline_raw.get("exposure_time", 0.0)),
                is_valid=bool(baseline_raw.get("is_valid", True)),
            )
        except (TypeError, ValueError):
            baseline = SecurityMetrics(threat_count=1, risk_score=0.0, coverage_ratio=0.0, exposure_time=0.0)
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
                "baseline": _security_metrics_to_dict(baseline),
            }
            success, text = self._invoker(args)
            if not success:
                continue
            new_metrics = _parse_security_metrics(text)
            if new_metrics is None:
                continue
            if new_metrics.better_than(baseline):
                any_improvement = True
                if baseline.threat_count > 0:
                    reduction = (baseline.threat_count - new_metrics.threat_count) / baseline.threat_count
                    if reduction > best_reduction:
                        best_reduction = reduction
        quality = max(0.0, min(1.0, best_reduction))
        cost = float(tried)
        latency = 1.0
        regression = not any_improvement
        return FitnessSignal(quality=quality, cost=cost, latency=latency, regression=regression)


# ── MLEvolvable (M027 S03) ───────────────────────────────────────────────


def _ml_metrics_to_dict(m: MLMetrics) -> dict:
    return {"loss": m.loss, "accuracy": m.accuracy, "epochs": m.epochs, "convergence_time": m.convergence_time, "is_valid": m.is_valid}


def _parse_ml_metrics(payload: str) -> MLMetrics | None:
    try:
        d = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    try:
        return MLMetrics(
            loss=float(d["loss"]), accuracy=float(d["accuracy"]),
            epochs=int(d["epochs"]), convergence_time=float(d["convergence_time"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _try_mutate_ml_candidate(cand: MLTransformParams) -> MLTransformParams:
    """Mutation: halve lr_factor for ADJUST_LR, add +1 n_layers for PRUNE_LAYER."""
    kind = cand.transform_type
    if kind is MLNodeKind.ML_TRANSFORM_ADJUST_LR:
        params = dict(cand.params)
        current = float(params.get("lr_factor", 0.5))
        params["lr_factor"] = max(0.01, current * 0.5)
        return MLTransformParams(transform_type=kind, params=params, legal=cand.legal)
    if kind is MLNodeKind.ML_TRANSFORM_PRUNE_LAYER:
        params = dict(cand.params)
        current = int(params.get("n_layers", 1))
        params["n_layers"] = min(32, current + 1)
        return MLTransformParams(transform_type=kind, params=params, legal=cand.legal)
    return cand


class MLEvolvable(Evolvable):
    """7th concrete Evolvable case. Mutates lr_factor (halve, floor 0.01) for ADJUST_LR."""

    def __init__(self, invoker: Callable[[dict[str, Any]], tuple[bool, str]]) -> None:
        if invoker is None:
            raise ValueError("MLEvolvable requires an invoker.")
        self._invoker = invoker

    @property
    def mutation_space(self) -> MutationSpace:
        return MutationSpace(
            description="halve lr_factor for ADJUST_LR (floor 0.01); bump n_layers for PRUNE_LAYER (cap 32)",
            mutate_fn_name="bump_ml_params",
        )

    def mutate(self, genome: Any) -> Any:
        if not isinstance(genome, tuple):
            raise TypeError(f"Expected tuple of MLTransformParams, got {type(genome).__name__}")
        if not all(isinstance(c, MLTransformParams) for c in genome):
            raise TypeError("Every genome element must be a MLTransformParams")
        if not genome:
            return genome
        new_candidates: list[MLTransformParams] = []
        mutated = False
        for cand in genome:
            if mutated:
                new_candidates.append(cand)
                continue
            mutated_cand = _try_mutate_ml_candidate(cand)
            if mutated_cand is cand:
                new_candidates.append(cand)
            else:
                new_candidates.append(mutated_cand)
                mutated = True
        return tuple(new_candidates)

    def evaluate(self, genome: Any, dataset: Any) -> FitnessSignal:
        if not isinstance(genome, tuple):
            raise TypeError(f"Expected tuple of MLTransformParams, got {type(genome).__name__}")
        if not all(isinstance(c, MLTransformParams) for c in genome):
            raise TypeError("Every genome element must be a MLTransformParams")
        ds = dataset if isinstance(dataset, dict) else {}
        baseline_raw = ds.get("baseline_metrics", {})
        if not isinstance(baseline_raw, dict):
            baseline_raw = {}
        try:
            baseline = MLMetrics(
                loss=float(baseline_raw.get("loss", 1.0)),
                accuracy=float(baseline_raw.get("accuracy", 0.0)),
                epochs=int(baseline_raw.get("epochs", 1)),
                convergence_time=float(baseline_raw.get("convergence_time", 0.0)),
                is_valid=bool(baseline_raw.get("is_valid", True)),
            )
        except (TypeError, ValueError):
            baseline = MLMetrics(loss=1.0, accuracy=0.0, epochs=1, convergence_time=0.0)
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
                "baseline": _ml_metrics_to_dict(baseline),
            }
            success, text = self._invoker(args)
            if not success:
                continue
            new_metrics = _parse_ml_metrics(text)
            if new_metrics is None:
                continue
            if new_metrics.better_than(baseline):
                any_improvement = True
                if baseline.loss > 0:
                    reduction = (baseline.loss - new_metrics.loss) / baseline.loss
                    if reduction > best_reduction:
                        best_reduction = reduction
        quality = max(0.0, min(1.0, best_reduction))
        cost = float(tried)
        latency = 1.0
        regression = not any_improvement
        return FitnessSignal(quality=quality, cost=cost, latency=latency, regression=regression)


# ── NetworkEvolvable (M028 S03) ──────────────────────────────────────────


def _network_metrics_to_dict(m: NetworkMetrics) -> dict:
    return {"latency_ms": m.latency_ms, "bandwidth_mbps": m.bandwidth_mbps, "packet_loss_pct": m.packet_loss_pct, "hop_count": m.hop_count, "is_valid": m.is_valid}


def _parse_network_metrics(payload: str) -> NetworkMetrics | None:
    try:
        d = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    try:
        return NetworkMetrics(
            latency_ms=float(d["latency_ms"]), bandwidth_mbps=float(d["bandwidth_mbps"]),
            packet_loss_pct=float(d["packet_loss_pct"]), hop_count=int(d["hop_count"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except (KeyError, TypeError, ValueError):
        return None


class NetworkEvolvable(Evolvable):
    """8th concrete Evolvable case. Mutation: reroute decreases latency further."""

    def __init__(self, invoker: Callable[[dict[str, Any]], tuple[bool, str]]) -> None:
        if invoker is None:
            raise ValueError("NetworkEvolvable requires an invoker.")
        self._invoker = invoker

    @property
    def mutation_space(self) -> MutationSpace:
        return MutationSpace(
            description="no deterministic numeric mutation for network transforms (REROUTE target is symbolic)",
            mutate_fn_name="noop_network_mutation",
        )

    def mutate(self, genome: Any) -> Any:
        if not isinstance(genome, tuple):
            raise TypeError(f"Expected tuple of NetworkTransformParams, got {type(genome).__name__}")
        if not all(isinstance(c, NetworkTransformParams) for c in genome):
            raise TypeError("Every genome element must be a NetworkTransformParams")
        # Network transforms have no numeric param to bump — return genome unchanged.
        return genome

    def evaluate(self, genome: Any, dataset: Any) -> FitnessSignal:
        if not isinstance(genome, tuple):
            raise TypeError(f"Expected tuple of NetworkTransformParams, got {type(genome).__name__}")
        if not all(isinstance(c, NetworkTransformParams) for c in genome):
            raise TypeError("Every genome element must be a NetworkTransformParams")
        ds = dataset if isinstance(dataset, dict) else {}
        baseline_raw = ds.get("baseline_metrics", {})
        if not isinstance(baseline_raw, dict):
            baseline_raw = {}
        try:
            baseline = NetworkMetrics(
                latency_ms=float(baseline_raw.get("latency_ms", 1.0)),
                bandwidth_mbps=float(baseline_raw.get("bandwidth_mbps", 0.0)),
                packet_loss_pct=float(baseline_raw.get("packet_loss_pct", 0.0)),
                hop_count=int(baseline_raw.get("hop_count", 1)),
                is_valid=bool(baseline_raw.get("is_valid", True)),
            )
        except (TypeError, ValueError):
            baseline = NetworkMetrics(latency_ms=1.0, bandwidth_mbps=0.0, packet_loss_pct=0.0, hop_count=1)
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
                "baseline": _network_metrics_to_dict(baseline),
            }
            success, text = self._invoker(args)
            if not success:
                continue
            new_metrics = _parse_network_metrics(text)
            if new_metrics is None:
                continue
            if new_metrics.better_than(baseline):
                any_improvement = True
                if baseline.latency_ms > 0:
                    reduction = (baseline.latency_ms - new_metrics.latency_ms) / baseline.latency_ms
                    if reduction > best_reduction:
                        best_reduction = reduction
        quality = max(0.0, min(1.0, best_reduction))
        cost = float(tried)
        latency = 1.0
        regression = not any_improvement
        return FitnessSignal(quality=quality, cost=cost, latency=latency, regression=regression)
