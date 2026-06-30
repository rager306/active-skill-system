"""L1 Domain — Fork and Diff types (M052 S08, D020).

Fork-and-diff primitives: branch any run at any event into an independent
fork, then structurally diff the fork against the parent. These are pure
domain dataclasses — the ForkEngine port (S09) uses them.

Pure domain. NO I/O, NO infrastructure imports (R002/R003). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Fork:
    """A fork specification: branch a run at a specific event.

    Fields:
      - parent_run_id: the source run to fork from.
      - fork_run_id: the new run created by the fork.
      - at_event_id: the event in the parent's log to fork at (inclusive).
      - config_overrides: what changed in the fork (e.g. {"model": "glm-5.2"}).
    """

    parent_run_id: str
    fork_run_id: str
    at_event_id: str
    config_overrides: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.parent_run_id, str) or not self.parent_run_id.strip():
            errors.append(f"parent_run_id must be non-empty string (got {self.parent_run_id!r})")
        if not isinstance(self.fork_run_id, str) or not self.fork_run_id.strip():
            errors.append(f"fork_run_id must be non-empty string (got {self.fork_run_id!r})")
        if not isinstance(self.at_event_id, str) or not self.at_event_id.strip():
            errors.append(f"at_event_id must be non-empty string (got {self.at_event_id!r})")
        if not isinstance(self.config_overrides, dict):
            errors.append(f"config_overrides must be dict (got {type(self.config_overrides).__name__})")
        if errors:
            raise ValueError("Fork invariant violation: " + "; ".join(errors))


@dataclass(frozen=True)
class DivergentObject:
    """An object that differs between parent and fork.

    Fields:
      - vertex_id: the id of the divergent vertex.
      - change_type: "added" | "removed" | "changed".
      - parent_data: the parent's version (None if added in fork).
      - fork_data: the fork's version (None if removed in fork).
    """

    vertex_id: str
    change_type: str
    parent_data: dict[str, Any] | None = None
    fork_data: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.vertex_id, str) or not self.vertex_id.strip():
            raise ValueError(f"vertex_id must be non-empty string (got {self.vertex_id!r})")
        if self.change_type not in ("added", "removed", "changed"):
            raise ValueError(f"change_type must be added/removed/changed (got {self.change_type!r})")

    def summary(self) -> str:
        """Human-readable one-line summary."""
        return f"{self.vertex_id}: {self.change_type}"


@dataclass(frozen=True)
class DivergentRelation:
    """A relation that differs between parent and fork."""

    edge_key: str
    change_type: str
    parent_data: dict[str, Any] | None = None
    fork_data: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.edge_key, str) or not self.edge_key.strip():
            raise ValueError(f"edge_key must be non-empty string (got {self.edge_key!r})")
        if self.change_type not in ("added", "removed", "changed"):
            raise ValueError(f"change_type must be added/removed/changed (got {self.change_type!r})")

    def summary(self) -> str:
        """Human-readable one-line summary."""
        return f"{self.edge_key}: {self.change_type}"


@dataclass(frozen=True)
class Diff:
    """Structural diff between a parent run and a fork.

    Fields:
      - parent_run_id: the source run.
      - fork_run_id: the forked run.
      - divergent_objects: objects that differ.
      - divergent_relations: relations that differ.
      - split_event_id: the event where the traces diverge (first different event).
    """

    parent_run_id: str
    fork_run_id: str
    divergent_objects: tuple[DivergentObject, ...] = ()
    divergent_relations: tuple[DivergentRelation, ...] = ()
    split_event_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.parent_run_id, str) or not self.parent_run_id.strip():
            raise ValueError(f"parent_run_id must be non-empty string (got {self.parent_run_id!r})")
        if not isinstance(self.fork_run_id, str) or not self.fork_run_id.strip():
            raise ValueError(f"fork_run_id must be non-empty string (got {self.fork_run_id!r})")

    @property
    def is_identical(self) -> bool:
        """True if parent and fork produced the same result."""
        return not self.divergent_objects and not self.divergent_relations

    def summary(self) -> str:
        """Human-readable multi-line diff summary."""
        lines = [
            f"diff: {self.parent_run_id} vs {self.fork_run_id}",
            f"  split event: {self.split_event_id or '(no divergence)'}",
            f"  divergent objects: {len(self.divergent_objects)}",
            f"  divergent relations: {len(self.divergent_relations)}",
        ]
        for obj in self.divergent_objects[:5]:
            lines.append(f"    {obj.summary()}")
        for rel in self.divergent_relations[:5]:
            lines.append(f"    {rel.summary()}")
        if len(self.divergent_objects) > 5 or len(self.divergent_relations) > 5:
            total = len(self.divergent_objects) + len(self.divergent_relations)
            lines.append(f"    ... and {total - 10} more")
        return "\n".join(lines)
