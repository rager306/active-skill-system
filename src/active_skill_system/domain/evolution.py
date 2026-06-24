"""L1 Domain - Evolution entity.

An Evolution is a derivation: a new genome (or expression) produced from
one or more parents by applying a Mutation. The Evolution records the
mutation, the parents, and the result (with a fitness score for selection).

Pure domain. NO I/O, NO infrastructure imports. Frozen dataclasses with
__post_init__ invariant validation.

This module depends only on stdlib + typing.
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from typing import Literal

from active_skill_system.domain.genome import GenomeId

# ── identifier ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvolutionId:
    """Identifier for an Evolution. Wraps a string for type safety."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:
            raise ValueError(f"EvolutionId.value must be a non-empty string (got {self.value!r})")

    def __str__(self) -> str:
        return self.value


# ── mutation ──────────────────────────────────────────────────────────────


_OPS = ("add", "remove", "modify")


@dataclass(frozen=True)
class Mutation:
    """A single atomic change applied during evolution.

    Carries:
      - op: one of "add" | "remove" | "modify".
      - target: name/path of the affected slot (e.g. "capabilities",
        "signature", a specific argument index).
      - value: new value (string form; None for "remove").
    """

    op: Literal["add", "remove", "modify"]
    target: str
    value: str | None = None

    def __post_init__(self) -> None:
        errors: list[str] = []
        if self.op not in _OPS:
            errors.append(f"Mutation.op must be one of {_OPS!r} (got {self.op!r})")
        if not isinstance(self.target, str) or not self.target:
            errors.append(f"Mutation.target must be a non-empty string (got {self.target!r})")
        if self.op == "remove" and self.value is not None:
            errors.append("Mutation.value must be None when op is 'remove'")
        if errors:
            raise ValueError("Mutation invariant violation: " + "; ".join(errors))


# ── invariants ────────────────────────────────────────────────────────────


ParentId = EvolutionId | GenomeId


def _fitness_in_unit_interval(e: Evolution) -> None:
    if not isinstance(e.fitness, (int, float)):
        raise ValueError(f"Evolution.fitness must be a number (got {type(e.fitness).__name__})")
    if not (0.0 <= float(e.fitness) <= 1.0):
        raise ValueError(f"Evolution.fitness must be in [0.0, 1.0] (got {e.fitness!r})")


def _parent_ids_non_empty(e: Evolution) -> None:
    if not e.parent_ids:
        raise ValueError("Evolution.parent_ids must be non-empty (at least one parent)")


def _parent_ids_are_hashable(e: Evolution) -> None:
    for pid in e.parent_ids:
        if not isinstance(pid, Hashable):
            raise ValueError(f"Evolution.parent_ids entries must be hashable (got {pid!r})")


def _child_id_not_in_parents(e: Evolution) -> None:
    if e.child_id in e.parent_ids:
        raise ValueError(f"Evolution.child_id ({e.child_id}) must not appear in parent_ids")


# ── the entity ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Evolution:
    """A derivation: a new genome/expression produced from parents.

    Carries:
      - parent_ids: non-empty tuple of parent ids (GenomeId or EvolutionId).
      - child_id: id of the result.
      - mutation: the Mutation applied to produce the child.
      - fitness: float in [0.0, 1.0] (selection signal).
    """

    parent_ids: tuple[ParentId, ...]
    child_id: EvolutionId
    mutation: Mutation
    fitness: float

    def __post_init__(self) -> None:
        errors: list[str] = []
        for check in (
            _fitness_in_unit_interval,
            _parent_ids_non_empty,
            _parent_ids_are_hashable,
            _child_id_not_in_parents,
        ):
            try:
                check(self)
            except ValueError as e:
                errors.append(str(e))
        if errors:
            raise ValueError(
                f"Evolution({self.child_id}) invariant violation: " + "; ".join(errors)
            )
