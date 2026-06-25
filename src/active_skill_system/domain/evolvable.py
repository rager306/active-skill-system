"""L1 Domain - Evolvable trait (M015 S01, D004).

Generic trait for tunable artifacts that can be mutated, evaluated, and
promoted through an offline evolution loop (D004). The trait abstracts:

  - genome: an immutable, versioned specification (ModelGenome, PromptGenome, etc.)
  - fitness: a FitnessSignal measuring quality/cost/latency/regression
  - mutation: a function that produces a variant of the genome
  - evaluation: measuring the fitness of a genome against a dataset

The EvolutionEngine (S03) operates generically over any Evolvable — it does
not know whether the genome is a prompt, a model config, or a repair policy.

Pure domain. NO I/O, NO infrastructure imports (R002). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class FitnessSignal:
    """Measured fitness of a genome against a dataset.

    Carries:
      - quality: [0.0, 1.0] — how good the genome performs (higher = better).
      - cost: >= 0.0 — cost per run (lower = better, e.g. tokens or USD).
      - latency: > 0.0 — time per run in ms (lower = better).
      - regression: True if the genome caused a regression vs baseline.
    """

    quality: float
    cost: float
    latency: float
    regression: bool = False

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.quality, int | float) or not (0.0 <= float(self.quality) <= 1.0):
            errors.append(f"quality must be in [0.0, 1.0] (got {self.quality!r})")
        if not isinstance(self.cost, int | float) or self.cost < 0:
            errors.append(f"cost must be >= 0.0 (got {self.cost!r})")
        if not isinstance(self.latency, int | float) or self.latency <= 0:
            errors.append(f"latency must be > 0.0 (got {self.latency!r})")
        if not isinstance(self.regression, bool):
            errors.append(f"regression must be a bool (got {type(self.regression).__name__})")
        if errors:
            raise ValueError("FitnessSignal invariant violation: " + "; ".join(errors))

    def better_than(self, other: FitnessSignal) -> bool:
        """True if this signal is strictly better than other.

        Better = higher quality AND (lower cost OR lower latency),
        with no regression. Ties in quality prefer lower cost.
        """
        if self.regression:
            return False
        if other.regression:
            return True
        if self.quality > other.quality:
            return True
        if self.quality == other.quality:
            return self.cost < other.cost or self.latency < other.latency
        return False


@dataclass(frozen=True)
class MutationSpace:
    """Describes how a genome can be mutated.

    Carries:
      - description: human-readable summary of mutation strategies.
      - mutate_fn_name: the name of the mutation function to call
        (e.g. "rephrase_template", "change_temperature", "add_few_shot").
    """

    description: str
    mutate_fn_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError(f"MutationSpace.description must be non-empty (got {self.description!r})")
        if not isinstance(self.mutate_fn_name, str) or not self.mutate_fn_name.strip():
            raise ValueError(f"MutationSpace.mutate_fn_name must be non-empty (got {self.mutate_fn_name!r})")


@runtime_checkable
class Evolvable(Protocol):
    """Generic trait for any artifact that can evolve offline (D004).

    Implementations: ModelGenomeEvolvable, PromptGenomeEvolvable,
    future: RepairPolicyEvolvable, TransformationGenomeEvolvable.

    The genome type is intentionally generic (``Any``) — each concrete
    evolvable defines its own genome type (ModelGenome, PromptGenome, etc.).
    The EvolutionEngine (S03) operates over Evolvable without knowing
    the concrete genome type.
    """

    @property
    def mutation_space(self) -> MutationSpace:
        """Description of how this genome can be mutated."""
        ...

    def mutate(self, genome: Any) -> Any:
        """Produce a variant of the genome. The caller decides which mutation."""
        ...

    def evaluate(self, genome: Any, dataset: Any) -> FitnessSignal:
        """Measure the fitness of a genome against a dataset."""
        ...
