"""L2 Application — MultiEvolvableEngine (M024 S01).

Runs multiple ``Evolvable`` adapters in a single ``MultiEvolvableEngine.run``
call, returning an aggregate ``MultiPromotionResult`` with the best
candidate across all genomes. Foundation for cross-domain evolution:
tune compiler transforms AND SQL plans simultaneously, pick the best
fitness signal across heterogeneous genomes.

Pure application. NO infrastructure imports (R002). Uses the existing
per-evolvable ``EvolutionEngine`` (M015 S03) under the hood — does not
duplicate its mutate/evaluate/promote logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from active_skill_system.application.evolution_engine import (
    EvolutionEngine,
    PromotionResult,
)
from active_skill_system.domain.evolvable import Evolvable


@dataclass(frozen=True)
class MultiPromotionResult:
    """Aggregate result of a multi-evolvable evolution run.

    Carries:
      - results: per-name PromotionResult from each EvolutionEngine.run.
      - best_name: name of the evolvable with the highest candidate_fitness.quality
        (or None if no candidate was promoted).
      - best_promoted: the PromotionResult for best_name (or None).
      - reason: human-readable summary.
    """

    results: dict[str, PromotionResult] = field(default_factory=dict)
    best_name: str | None = None
    best_promoted: PromotionResult | None = None
    reason: str = ""


class MultiEvolvableEngine:
    """Runs multiple Evolvables and returns an aggregate MultiPromotionResult.

    Each ``(evolvable, baseline_genome)`` pair is run through the existing
    ``EvolutionEngine`` in isolation — no shared state across evolvables.
    The best candidate is selected by ``candidate_fitness.quality``
    (highest wins; ties broken by lowest cost).

    Usage::

        engine = MultiEvolvableEngine()
        result = engine.run(
            evolvables={
                "compiler": (compiler_evolvable, compiler_baseline),
                "sql":      (sql_evolvable, sql_baseline),
            },
            datasets={
                "compiler": compiler_dataset,
                "sql":      sql_dataset,
            },
            max_iterations=5,
        )
        if result.best_promoted is not None:
            best_genome = result.best_promoted.promoted_genome
    """

    def __init__(self, engine: EvolutionEngine | None = None) -> None:
        self._engine = engine if engine is not None else EvolutionEngine()

    def run(
        self,
        evolvables: dict[str, tuple[Evolvable, Any]],
        datasets: dict[str, Any],
        *,
        max_iterations: int = 10,
    ) -> MultiPromotionResult:
        """Run evolution over each evolvable and return the aggregate result.

        Args:
            evolvables: dict mapping name -> (evolvable, baseline_genome).
            datasets: dict mapping name -> dataset. A name must be present
                here iff it is in ``evolvables``.
            max_iterations: max mutation-evaluation cycles per evolvable.

        Returns:
            MultiPromotionResult with per-name PromotionResults and the best
            across all names by candidate_fitness.quality.
        """
        if not isinstance(evolvables, dict):
            raise TypeError(f"evolvables must be a dict (got {type(evolvables).__name__})")
        if not isinstance(datasets, dict):
            raise TypeError(f"datasets must be a dict (got {type(datasets).__name__})")
        if max_iterations < 1:
            raise ValueError(f"max_iterations must be >= 1 (got {max_iterations!r})")

        results: dict[str, PromotionResult] = {}
        for name, pair in evolvables.items():
            if not isinstance(name, str) or not name:
                raise ValueError(f"evolvables keys must be non-empty strings (got {name!r})")
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError(
                    f"evolvables[{name!r}] must be a (evolvable, baseline_genome) tuple"
                )
            evolvable, baseline_genome = pair
            if not isinstance(evolvable, Evolvable):
                raise TypeError(
                    f"evolvables[{name!r}][0] must satisfy the Evolvable Protocol"
                )
            dataset = datasets.get(name)
            if dataset is None and name in datasets:
                dataset = datasets[name]
            result = self._engine.run(
                evolvable=evolvable,
                baseline_genome=baseline_genome,
                dataset=dataset if dataset is not None else {},
                max_iterations=max_iterations,
            )
            results[name] = result

        # Pick the best promoted candidate by candidate_fitness.quality.
        # Ties broken by lowest cost; further ties by first-seen name (stable).
        best_name: str | None = None
        best_promoted: PromotionResult | None = None
        best_quality = float("-inf")
        best_cost = float("inf")
        for name, r in results.items():
            if not r.promoted:
                continue
            q = r.candidate_fitness.quality
            c = r.candidate_fitness.cost
            if q > best_quality or (q == best_quality and c < best_cost):
                best_name = name
                best_promoted = r
                best_quality = q
                best_cost = c

        if best_promoted is None:
            reason = (
                f"No promotion across {len(results)} evolvable(s) "
                f"after {max_iterations} iteration(s) each"
            )
        else:
            promoted_count = sum(1 for r in results.values() if r.promoted)
            reason = (
                f"Best promotion: {best_name!r} "
                f"(quality={best_quality:.4f}, cost={best_cost:.2f}); "
                f"{promoted_count}/{len(results)} evolvable(s) promoted"
            )

        return MultiPromotionResult(
            results=results,
            best_name=best_name,
            best_promoted=best_promoted,
            reason=reason,
        )
