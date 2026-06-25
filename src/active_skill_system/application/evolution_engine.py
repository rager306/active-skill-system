"""L2 Application — EvolutionEngine (M015 S03, D004).

Generic offline evolution loop: mutate → evaluate → select → promote.
Operates over any ``Evolvable`` — does not know whether the genome is a
ModelGenome, PromptGenome, or future RepairPolicyGenome.

Promotion gate: baseline-ratchet semantics (D004/D002). A candidate is
promoted only if its fitness is **strictly better** than the baseline
(``FitnessSignal.better_than``). This prevents regression drift — the
ratchet can only move up.

Pure application. Depends on domain (Evolvable, FitnessSignal); no I/O (R002).
"""

from __future__ import annotations

from dataclasses import dataclass

from active_skill_system.domain.evolvable import Evolvable, FitnessSignal


@dataclass(frozen=True)
class PromotionResult:
    """Result of an evolution run.

    Carries:
      - promoted: True if a candidate was promoted over the baseline.
      - promoted_genome: the promoted genome (or baseline if not promoted).
      - baseline_fitness: the baseline's fitness signal.
      - candidate_fitness: the best candidate's fitness signal (or baseline if none).
      - iterations_used: how many mutation-evaluation cycles ran.
      - reason: human-readable summary of the outcome.
    """

    promoted: bool
    promoted_genome: object
    baseline_fitness: FitnessSignal
    candidate_fitness: FitnessSignal
    iterations_used: int
    reason: str


class EvolutionEngine:
    """Generic offline evolution engine (D004).

    Usage::

        engine = EvolutionEngine()
        result = engine.run(
            evolvable=model_evolvable,
            baseline_genome=m3_genome,
            dataset={"success_rate": 0.7, "avg_latency_ms": 200},
            max_iterations=5,
        )
        if result.promoted:
            new_genome = result.promoted_genome
    """

    def run(
        self,
        evolvable: Evolvable,
        baseline_genome: object,
        dataset: object,
        *,
        max_iterations: int = 10,
    ) -> PromotionResult:
        """Run the evolution loop.

        Args:
            evolvable: the Evolvable adapter (provides mutate + evaluate).
            baseline_genome: the current genome to improve.
            dataset: evaluation dataset (format defined by the Evolvable).
            max_iterations: max mutation-evaluation cycles.

        Returns:
            PromotionResult with the outcome.
        """
        baseline_fitness = evolvable.evaluate(baseline_genome, dataset)

        best_genome = baseline_genome
        best_fitness = baseline_fitness

        for i in range(max_iterations):
            candidate = evolvable.mutate(best_genome)
            candidate_fitness = evolvable.evaluate(candidate, dataset)

            if candidate_fitness.better_than(best_fitness):
                best_genome = candidate
                best_fitness = candidate_fitness
                # Promote immediately on first improvement (greedy).
                return PromotionResult(
                    promoted=True,
                    promoted_genome=best_genome,
                    baseline_fitness=baseline_fitness,
                    candidate_fitness=best_fitness,
                    iterations_used=i + 1,
                    reason=f"Candidate promoted at iteration {i + 1}: "
                    f"quality {baseline_fitness.quality:.2f}→{best_fitness.quality:.2f}, "
                    f"cost {baseline_fitness.cost:.2f}→{best_fitness.cost:.2f}",
                )

        # No improvement after all iterations.
        return PromotionResult(
            promoted=False,
            promoted_genome=baseline_genome,
            baseline_fitness=baseline_fitness,
            candidate_fitness=best_fitness,
            iterations_used=max_iterations,
            reason=f"No improvement after {max_iterations} iterations (baseline retained)",
        )
