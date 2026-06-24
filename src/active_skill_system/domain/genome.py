"""L1 Domain - Genome entity.

A Genome is a self-contained unit of capability in the Active Skill System.
It carries a signature (the executable form), a set of capabilities it can
exercise, and a list of invariants that must hold for any Expression
derived from it.

Pure domain. NO I/O, NO infrastructure imports. Frozen dataclass with
__post_init__ invariant validation; violations raise ValueError.

This module depends only on stdlib + typing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ── identifier ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GenomeId:
    """Identifier for a Genome. Wraps a string for type safety."""

    value: str

    def __post_init__(self) -> None:
        _non_empty_str("GenomeId.value", self.value)

    def __str__(self) -> str:
        return self.value


# ── invariants (module-private helpers) ───────────────────────────────────


def _non_empty_str(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string (got {value!r})")


def _non_empty_set(field_name: str, value: Any) -> None:
    if not isinstance(value, (set, frozenset)) or len(value) == 0:
        raise ValueError(f"{field_name} must be a non-empty set/frozenset (got {value!r})")


def _signature_non_empty(g: Genome) -> None:
    _non_empty_str("Genome.signature", g.signature)


def _name_non_empty(g: Genome) -> None:
    _non_empty_str("Genome.name", g.name)


def _capabilities_non_empty(g: Genome) -> None:
    _non_empty_set("Genome.capabilities", g.capabilities)


# ── the entity ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Genome:
    """A self-contained unit of capability.

    Carries:
      - id: unique identifier (GenomeId).
      - name: human-readable short name (non-empty).
      - signature: the executable form (non-empty string; for our purpose
        this is opaque text - the runtime decides how to interpret it).
      - capabilities: frozenset of capability tags the genome exercises.
        Non-empty (a genome that can do nothing is not a useful unit).
      - invariants: tuple of callables (genome -> None) that must hold for
        any Expression derived from this genome. Default: empty tuple
        (the four built-in invariants are always enforced via __post_init__).

    All fields are immutable (frozen). __post_init__ enforces the four
    built-in invariants; violations raise ValueError. Per-instance
    `invariants` are exposed for the application layer to re-check.
    """

    id: GenomeId
    name: str
    signature: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    invariants: tuple[Callable[[Genome], None], ...] = ()

    def __post_init__(self) -> None:
        errors: list[str] = []
        for check in (_signature_non_empty, _name_non_empty, _capabilities_non_empty):
            try:
                check(self)
            except ValueError as e:
                errors.append(str(e))
        if errors:
            raise ValueError(f"Genome({self.id}) invariant violation: " + "; ".join(errors))

    def check_invariants(self) -> None:
        """Run the per-instance invariant checks. Raises ValueError on first failure."""
        for check in self.invariants:
            check(self)
