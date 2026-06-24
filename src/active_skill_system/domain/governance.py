"""L1 Domain - Governance policy.

GovernancePolicy captures the policy constraints a runtime must enforce
during evolution: max evolution depth (how many generations are allowed),
review threshold (fitness below which a human must review), and a frozen
flag (when True, the runtime rejects any further mutations).

Pure domain. NO I/O, NO infrastructure imports. Frozen dataclass with
__post_init__ invariant validation; classmethod default_policy() returns
sensible defaults.

This module depends only on stdlib + typing.
"""

from __future__ import annotations

from dataclasses import dataclass


def _max_evolution_depth_positive(p: GovernancePolicy) -> None:
    if not isinstance(p.max_evolution_depth, int) or isinstance(p.max_evolution_depth, bool):
        raise ValueError(
            f"GovernancePolicy.max_evolution_depth must be an int (got "
            f"{type(p.max_evolution_depth).__name__})"
        )
    if p.max_evolution_depth < 1:
        raise ValueError(
            f"GovernancePolicy.max_evolution_depth must be >= 1 (got {p.max_evolution_depth})"
        )


def _review_threshold_in_unit_interval(p: GovernancePolicy) -> None:
    if not isinstance(p.review_threshold, (int, float)):
        raise ValueError(
            f"GovernancePolicy.review_threshold must be a number (got "
            f"{type(p.review_threshold).__name__})"
        )
    if not (0.0 <= float(p.review_threshold) <= 1.0):
        raise ValueError(
            f"GovernancePolicy.review_threshold must be in [0.0, 1.0] (got {p.review_threshold!r})"
        )


@dataclass(frozen=True)
class GovernancePolicy:
    """Policy constraints enforced by the runtime during evolution.

    Carries:
      - max_evolution_depth: int >= 1 (max generations).
      - review_threshold: float in [0.0, 1.0] (fitness below which
        human review is required).
      - frozen: bool (when True, the runtime rejects any further
        mutations on governed genomes).
    """

    max_evolution_depth: int
    review_threshold: float
    frozen: bool = False

    def __post_init__(self) -> None:
        errors: list[str] = []
        for check in (_max_evolution_depth_positive, _review_threshold_in_unit_interval):
            try:
                check(self)
            except ValueError as e:
                errors.append(str(e))
        if errors:
            raise ValueError("GovernancePolicy invariant violation: " + "; ".join(errors))

    @classmethod
    def default_policy(cls) -> GovernancePolicy:
        """Return a sensible default (depth=5, threshold=0.7, not frozen)."""
        return cls(max_evolution_depth=5, review_threshold=0.7, frozen=False)
