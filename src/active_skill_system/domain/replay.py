"""L1 Domain — ReplayResult (M054 S01, Wave D primitive #10).

The result of replaying an event log into a graph. Carries the reconstructed
graph state, the events that were replayed, and (in permissive mode) the
behaviors that fired during replay.

Pure domain. NO I/O, NO infrastructure imports (R002/R003). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ReplayMode:
    """How events are replayed into the graph."""

    STRICT = "strict"          # replay events WITHOUT firing behaviors (pure reconstruction)
    PERMISSIVE = "permissive"  # replay events AND fire behaviors (as if events are new)


@dataclass(frozen=True)
class ReplayResult:
    """The outcome of replaying an event log.

    Fields:
      - run_id: the run that was replayed.
      - mode: ReplayMode (strict or permissive).
      - events_replayed: number of events processed.
      - vertices_reconstructed: number of vertices in the reconstructed graph.
      - edges_reconstructed: number of edges in the reconstructed graph.
      - behaviors_fired: number of behaviors that fired (0 in strict mode).
      - duration_ns: how long the replay took (nanoseconds).
      - graph_snapshot: the reconstructed graph state (dict of vertex_id -> data).
    """

    run_id: str
    mode: str
    events_replayed: int = 0
    vertices_reconstructed: int = 0
    edges_reconstructed: int = 0
    behaviors_fired: int = 0
    duration_ns: int = 0
    graph_snapshot: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            errors.append(f"run_id must be non-empty string (got {self.run_id!r})")
        if self.mode not in (ReplayMode.STRICT, ReplayMode.PERMISSIVE):
            errors.append(f"mode must be strict/permissive (got {self.mode!r})")
        if not isinstance(self.events_replayed, int) or self.events_replayed < 0:
            errors.append(f"events_replayed must be non-negative int (got {self.events_replayed!r})")
        if not isinstance(self.vertices_reconstructed, int) or self.vertices_reconstructed < 0:
            errors.append("vertices_reconstructed must be non-negative int")
        if not isinstance(self.behaviors_fired, int) or self.behaviors_fired < 0:
            errors.append("behaviors_fired must be non-negative int")
        if not isinstance(self.duration_ns, int) or self.duration_ns < 0:
            errors.append("duration_ns must be non-negative int")
        if errors:
            raise ValueError("ReplayResult invariant violation: " + "; ".join(errors))

    def summary(self) -> str:
        """Human-readable one-line summary."""
        return (
            f"replay {self.mode} run={self.run_id}: "
            f"{self.events_replayed} events → "
            f"{self.vertices_reconstructed} vertices, "
            f"{self.edges_reconstructed} edges, "
            f"{self.behaviors_fired} behaviors fired"
        )
