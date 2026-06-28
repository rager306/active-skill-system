"""L2 Application — GraphBackend port (M051 S01, Wave A).

The swappable graph-storage seam. Speaks GENERIC ``Vertex``/``Edge`` types
(from ``domain/graph_primitives.py``), not Loop-specific ones and not any
backend's Cypher/Gremlin/GraphQL dialect.

Adapters translate to the backend's native language:
  - ``LadybugBackend`` (LadybugDB, Cypher) — current default.
  - ``HelixBackend`` (HelixDB, GraphQL+Cypher hybrid) — future.
  - ``FalkorBackend`` (FalkorDB, Cypher over Redis) — future.

The application depends on THIS port, never on a concrete backend. This is
the swap seam that makes HelixDB/FalkorDB a one-adapter-file change.

Distinct from the existing ``GraphStore`` port: ``GraphStore`` is a thin
facade that delegates to ``GraphBackend`` and exists only to keep 50
milestones of Loop-specific callers working unchanged.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from active_skill_system.domain.graph_primitives import Edge, Vertex


@runtime_checkable
class GraphBackend(Protocol):
    """Generic, dialect-agnostic graph storage.

    Implementations MUST be idempotent on vertex id and (edge kind, src, dst):
    upserting the same vertex/edge twice yields the same stored state, no
    duplicates.
    """

    def upsert_vertex(self, v: Vertex) -> None:
        """Insert or update a vertex by id."""
        ...

    def upsert_edge(self, e: Edge) -> None:
        """Insert or update an edge by (kind, src, dst)."""
        ...

    def get_vertex(self, vid: str) -> Vertex | None:
        """Return the vertex with ``vid``, or None if absent."""
        ...

    def neighbours(self, vid: str, *, direction: str = "out") -> tuple[Vertex, ...]:
        """Return neighbouring vertices of ``vid``.

        Args:
            vid: the vertex to traverse from.
            direction: ``"out"`` (default), ``"in"``, or ``"both"``.
        """
        ...

    def has_edge(self, kind: str, src: str, dst: str) -> bool:
        """True iff an edge of ``kind`` from ``src`` to ``dst`` is stored."""
        ...

    def count_vertices(self) -> int:
        """Number of stored vertices."""
        ...

    def count_edges(self) -> int:
        """Number of stored edges."""
        ...

    def all_vertex_ids(self) -> tuple[str, ...]:
        """All stored vertex ids (snapshot). Empty tuple if unsupported."""
        ...

    def count_edges_of_kind(self, kind: str) -> int:
        """Count edges whose kind matches. 0 if unsupported."""
        ...
