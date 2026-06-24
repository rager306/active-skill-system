"""L1 Domain - versioned immutable TaskGraph (Cognitive Runtime bounded context).

The TaskGraph is the reasoning structure: typed nodes + typed edges. It is
**immutable**: every mutation (add_node / add_edge / commit) returns a NEW
graph with an incremented version. Versioning is monotonic and parent-linked,
so the full history of a reasoning run is reconstructable (concept.md F-04).

``commit`` snapshots the current graph as a new version (parent_version = the
previous version). This is the mechanism the application layer uses to advance
the graph through the reasoning loop while preserving prior versions.

Pure domain. NO I/O, NO infrastructure imports (R002). Frozen dataclass with
``__post_init__`` invariant validation. stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass

from active_skill_system.domain.runtime.edges import TaskEdge
from active_skill_system.domain.runtime.nodes import TaskNode


def _dangling_edges(nodes: frozenset[TaskNode], edges: frozenset[TaskEdge]) -> list[TaskEdge]:
    """Return edges referencing nodes not present in the node set."""
    ids = {n.id for n in nodes}
    return [e for e in edges if e.source not in ids or e.target not in ids]


@dataclass(frozen=True)
class TaskGraph:
    """An immutable, versioned reasoning graph.

    Carries:
      - nodes: frozenset of TaskNode (empty by default for v0).
      - edges: frozenset of TaskEdge (empty by default).
      - version: monotonic version counter (starts at 0).
      - parent_version: the version this one was derived from (None for v0).

    Invariants:
      - every edge references nodes present in ``nodes`` (no dangling edges).
      - version >= 0; parent_version is None only at version 0.
    """

    nodes: frozenset[TaskNode] = frozenset()
    edges: frozenset[TaskEdge] = frozenset()
    version: int = 0
    parent_version: int | None = None

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 0:
            errors.append(f"version must be a non-negative int (got {self.version!r})")
        if self.version == 0 and self.parent_version is not None:
            errors.append("parent_version must be None at version 0")
        if self.version > 0 and (not isinstance(self.parent_version, int) or self.parent_version < 0):
            errors.append(
                f"parent_version must be a non-negative int when version > 0 (got {self.parent_version!r})"
            )
        dangling = _dangling_edges(self.nodes, self.edges)
        if dangling:
            errors.append(
                f"{len(dangling)} edge(s) reference unknown nodes: "
                + ", ".join(f"{e.source}->{e.target}" for e in dangling[:3])
            )
        if errors:
            raise ValueError(f"TaskGraph(v{self.version}) invariant violation: " + "; ".join(errors))

    def has(self, node_id) -> bool:  # noqa: ANN001
        return any(n.id == node_id for n in self.nodes)

    def add_node(self, node: TaskNode) -> TaskGraph:
        """Return a new graph with ``node`` added at version+1."""
        if not isinstance(node, TaskNode):
            raise ValueError(f"add_node expects a TaskNode (got {type(node).__name__})")
        return TaskGraph(
            nodes=self.nodes | {node},
            edges=self.edges,
            version=self.version + 1,
            parent_version=self.version,
        )

    def add_edge(self, edge: TaskEdge) -> TaskGraph:
        """Return a new graph with ``edge`` added at version+1.

        The edge's endpoints must already be present (or the new graph would
        contain a dangling edge, which __post_init__ rejects).
        """
        if not isinstance(edge, TaskEdge):
            raise ValueError(f"add_edge expects a TaskEdge (got {type(edge).__name__})")
        return TaskGraph(
            nodes=self.nodes,
            edges=self.edges | {edge},
            version=self.version + 1,
            parent_version=self.version,
        )

    def commit(self) -> TaskGraph:
        """Snapshot the current graph as a new version (no structural change)."""
        return TaskGraph(
            nodes=self.nodes,
            edges=self.edges,
            version=self.version + 1,
            parent_version=self.version,
        )
