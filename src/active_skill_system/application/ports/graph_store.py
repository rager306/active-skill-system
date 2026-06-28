"""L2 Application — GraphStore outbound port (RGLA, D010).

The port the application depends on for LoopGraph persistence. L3 adapters
(e.g. ``adapters/ladybug_graph_store.LadybugGraphStore``) implement it. The
domain ``LoopGraph`` type (D009 §4.2) is what is stored; the port stays
infrastructure-free (R002) — it references only domain + stdlib types.

Design (D010):
  - The domain never imports a database; it produces a ``LoopGraph`` projection.
  - The adapter owns the concrete store (LadybugDB ``:memory:`` for tests,
    ``.lbdb`` for opt-in disk persistence).
  - The port is the swap seam: if LadybugDB stalls (D010 maturity caveat), a
    different adapter replaces it without touching domain/application.

Read/write shape mirrors the append-only provenance discipline (D009 §4.2):
``store_loop_graph`` is idempotent on vertex/edge identity; ``query_neighbours``
is a read-only traversal.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from active_skill_system.domain.loop_graph import LoopEdge, LoopGraph, LoopVertex


@runtime_checkable
class GraphStore(Protocol):
    """Persistence port for LoopGraph vertices and edges (D010).

    Implementations MUST be idempotent on (vertex id) and (edge kind, src, dst):
    storing the same graph twice yields the same stored state, with no duplicate
    vertices/edges. This keeps the append-only provenance projection sound
    (D009 §4.2) and makes ``store_loop_graph`` safe to call after every Loop
    transition.
    """

    def store_loop_graph(self, graph: LoopGraph) -> None:
        """Persist (upsert) all vertices and edges of ``graph``.

        Args:
            graph: the LoopGraph projection to store.
        """
        ...

    def store_vertex(self, vertex: LoopVertex) -> None:
        """Upsert a single vertex by id."""
        ...

    def store_edge(self, edge: LoopEdge) -> None:
        """Upsert a single edge by (kind, src, dst)."""
        ...

    def get_vertex(self, vertex_id: str) -> LoopVertex | None:
        """Return the vertex with ``vertex_id``, or None if absent."""
        ...

    def query_neighbours(
        self,
        vertex_id: str,
        *,
        direction: str = "out",
    ) -> tuple[LoopVertex, ...]:
        """Return neighbouring vertices of ``vertex_id``.

        Args:
            vertex_id: the vertex to traverse from.
            direction: ``"out"`` (default), ``"in"``, or ``"both"``.
        """
        ...

    def has_edge(self, kind: object, src: str, dst: str) -> bool:
        """True iff an edge of ``kind`` from ``src`` to ``dst`` is stored."""
        ...

    def count_vertices(self) -> int:
        """Number of stored vertices."""
        ...

    def count_edges(self) -> int:
        """Number of stored edges."""
        ...

    def list_vertex_ids(self) -> tuple[str, ...]:
        """All stored vertex ids (read-only snapshot).

        Used by aggregation use-cases (ReportReader, Recommender) that need
        to scan vertex kinds/labels. Adapters may return an empty tuple
        when the backing store cannot enumerate.
        """
        ...

    def count_edges_by_kind(self, kind_value: str) -> int:
        """Count edges of a given kind (e.g. 'created', 'verified_by').

        Adapters backed by Cypher-backed stores can issue a precise
        MATCH..RETURN count; in-memory adapters may scan. Returns 0 when
        the store cannot enumerate.
        """
        ...
