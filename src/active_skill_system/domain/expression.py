"""L1 Domain - Expression entity.

An Expression is a concrete invocation of a Genome. It carries the
arguments used, when it was produced, which evidences it produced (or
was produced by), and its status.

Pure domain. NO I/O, NO infrastructure imports. Frozen dataclass with
__post_init__ invariant validation; violations raise ValueError.

This module depends only on stdlib + typing.
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from active_skill_system.domain.genome import GenomeId

# ── identifier ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExpressionId:
    """Identifier for an Expression. Wraps a string for type safety."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:
            raise ValueError(f"ExpressionId.value must be a non-empty string (got {self.value!r})")

    def __str__(self) -> str:
        return self.value


# ── invariants ────────────────────────────────────────────────────────────


_STATUSES = ("ok", "failed", "pending")


def _status_valid(e: Expression) -> None:
    if e.status not in _STATUSES:
        raise ValueError(f"Expression.status must be one of {_STATUSES!r} (got {e.status!r})")


def _evidence_ids_unique(e: Expression) -> None:
    if len(e.evidence_ids) != len(set(e.evidence_ids)):
        raise ValueError("Expression.evidence_ids must be unique (duplicates found)")


def _evidence_ids_are_hashable(e: Expression) -> None:
    for eid in e.evidence_ids:
        if not isinstance(eid, Hashable):
            raise ValueError(f"Expression.evidence_ids entries must be hashable (got {eid!r})")


def _args_finite(e: Expression) -> None:
    # Cap on argument count to keep domain objects reasonable.
    # (Payload size is a runtime concern, not domain.)
    if len(e.args) > 64:
        raise ValueError(f"Expression.args has {len(e.args)} items; domain cap is 64")


# ── the entity ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Expression:
    """A concrete invocation of a Genome.

    Carries:
      - id: unique identifier (ExpressionId).
      - genome_id: which genome was expressed.
      - args: tuple of arguments (heterogeneous; cap at 64 items).
      - produced_at: timestamp (UTC, tz-aware).
      - evidence_ids: tuple of expression ids that serve as evidence for
        this expression (must be unique and hashable).
      - status: one of "ok" | "failed" | "pending".

    All fields are immutable (frozen). __post_init__ enforces the four
    built-in invariants; violations raise ValueError.
    """

    id: ExpressionId
    genome_id: GenomeId
    args: tuple[Any, ...] = ()
    produced_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    evidence_ids: tuple[ExpressionId, ...] = ()
    status: Literal["ok", "failed", "pending"] = "pending"

    def __post_init__(self) -> None:
        errors: list[str] = []
        for check in (
            _status_valid,
            _evidence_ids_unique,
            _evidence_ids_are_hashable,
            _args_finite,
        ):
            try:
                check(self)
            except ValueError as e:
                errors.append(str(e))
        if errors:
            raise ValueError(f"Expression({self.id}) invariant violation: " + "; ".join(errors))
