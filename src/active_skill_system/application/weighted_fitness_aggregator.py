"""L2 Application — WeightedFitnessAggregator (M025 S01).

Combines multiple ``FitnessSignal`` values into a single weighted score.
Enables multi-objective optimization: rank candidates by
``cycles * 0.5 + spills * 0.3 + cache_misses * 0.2`` instead of a single
quality axis. Returns a ``WeightedFitnessScore`` frozen dataclass.

Pure application. NO infrastructure imports (R002).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from active_skill_system.domain.evolvable import FitnessSignal

# Tolerance for weight-sum validation: weights must sum to ~1.0.
_WEIGHT_SUM_TOLERANCE: float = 1e-6


@dataclass(frozen=True)
class WeightedFitnessScore:
    """Aggregate weighted fitness score across multiple axes.

    Carries:
      - score: weighted sum of per-axis quality values, in [0.0, 1.0].
      - contributions: per-axis contribution to the final score (weight * quality).
      - regression: True iff ANY contributing signal has regression=True.
      - reason: human-readable summary.
    """

    score: float
    contributions: dict[str, float] = field(default_factory=dict)
    regression: bool = False
    reason: str = ""

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.score, (int, float)) or isinstance(self.score, bool):
            errors.append(f"score must be a number (got {type(self.score).__name__})")
        elif not (0.0 <= float(self.score) <= 1.0):
            errors.append(f"score must be in [0.0, 1.0] (got {self.score!r})")
        if not isinstance(self.contributions, dict):
            errors.append(f"contributions must be a dict (got {type(self.contributions).__name__})")
        if not isinstance(self.regression, bool):
            errors.append(f"regression must be a bool (got {type(self.regression).__name__})")
        if not isinstance(self.reason, str):
            errors.append(f"reason must be a string (got {type(self.reason).__name__})")
        if errors:
            raise ValueError("WeightedFitnessScore invariant violation: " + "; ".join(errors))


class WeightedFitnessAggregator:
    """Aggregates multiple FitnessSignals into a single WeightedFitnessScore.

    Weights must sum to ~1.0 (within ``_WEIGHT_SUM_TOLERANCE``). The
    aggregated score is the weighted sum of per-axis quality values,
    clamped to [0.0, 1.0]. The ``regression`` flag is True iff ANY
    contributing signal has ``regression=True`` — so any regression
    blocks promotion even if the weighted score is high.
    """

    def __init__(self, weights: dict[str, float]) -> None:
        if not isinstance(weights, dict):
            raise TypeError(f"weights must be a dict (got {type(weights).__name__})")
        if not weights:
            raise ValueError("weights must be non-empty")
        errors: list[str] = []
        for name, w in weights.items():
            if not isinstance(name, str) or not name:
                errors.append(f"weight key must be non-empty string (got {name!r})")
            if not isinstance(w, (int, float)) or isinstance(w, bool):
                errors.append(f"weight[{name!r}] must be a number (got {type(w).__name__})")
            elif w < 0.0:
                errors.append(f"weight[{name!r}] must be non-negative (got {w!r})")
        weight_sum = sum(float(w) for w in weights.values())
        if abs(weight_sum - 1.0) > _WEIGHT_SUM_TOLERANCE:
            errors.append(
                f"weights must sum to 1.0 (got sum={weight_sum!r}); "
                "normalize or adjust weights"
            )
        if errors:
            raise ValueError("WeightedFitnessAggregator invariant violation: " + "; ".join(errors))
        self._weights: dict[str, float] = {k: float(v) for k, v in weights.items()}

    @property
    def weights(self) -> dict[str, float]:
        return dict(self._weights)

    def aggregate(self, signals: dict[str, FitnessSignal]) -> WeightedFitnessScore:
        """Aggregate ``signals`` into a WeightedFitnessScore.

        Signals not in the weight dict are ignored. Missing signals for
        known weights contribute 0.0 to the score.
        """
        if not isinstance(signals, dict):
            raise TypeError(f"signals must be a dict (got {type(signals).__name__})")
        contributions: dict[str, float] = {}
        total = 0.0
        any_regression = False
        contributing = 0
        for name, weight in self._weights.items():
            signal = signals.get(name)
            if signal is None:
                contributions[name] = 0.0
                continue
            if not isinstance(signal, FitnessSignal):
                raise TypeError(f"signals[{name!r}] must be a FitnessSignal (got {type(signal).__name__})")
            contribution = weight * float(signal.quality)
            contributions[name] = contribution
            total += contribution
            if signal.regression:
                any_regression = True
            contributing += 1
        score = max(0.0, min(1.0, total))
        if contributing == 0:
            reason = "No signals matched the weight vector"
        elif any_regression:
            reason = f"Weighted score {score:.4f} (BLOCKED: at least one axis regressed)"
        else:
            reason = f"Weighted score {score:.4f} across {contributing} axis/axes"
        return WeightedFitnessScore(
            score=score,
            contributions=contributions,
            regression=any_regression,
            reason=reason,
        )
