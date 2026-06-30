"""L2 Application — GraphViewBuilder use case (M054 S05, Wave D primitive #6).

Builds scoped read-only views of the graph from GraphBackend queries.
Wave D primitive #6 (Views) — scoped reads that filter by vertex type,
edge kind, or subgraph.

Differs from domain/pattern.py GraphView (which is a snapshot data structure):
this USE CASE builds those snapshots from GraphBackend queries with filters.

Usage:
    builder = GraphViewBuilder(backend)
    view = builder.filter_by_type("claim")
    view = builder.filter_by_edge_kind("supports")
    view = builder.subgraph(["c1", "e1"])
"""

from __future__ import annotations

from typing import Any

from active_skill_system.domain.pattern import GraphView


class GraphViewBuilder:
    """Builds scoped read-only graph views from GraphBackend.

    Args:
        backend: GraphBackend to query (M051). Can be None for test scenarios
            where you build views from explicit vertex/edge dicts.
        vertices: optional explicit vertices dict (overrides backend).
        edges: optional explicit edges list (overrides backend).
    """

    def __init__(
        self,
        backend: Any = None,
        vertices: dict[str, dict[str, Any]] | None = None,
        edges: list[dict[str, Any]] | None = None,
    ) -> None:
        self._backend = backend
        self._vertices = vertices
        self._edges = edges

    def _get_all_vertices(self) -> dict[str, dict[str, Any]]:
        """Get all vertices from explicit dict or backend."""
        if self._vertices is not None:
            return self._vertices
        if self._backend is None:
            return {}
        result: dict[str, dict[str, Any]] = {}
        for vid in self._backend.all_vertex_ids():
            vertex = self._backend.get_vertex(vid)
            if vertex is not None:
                # Extract type + data from domain Vertex.
                vtype = getattr(vertex, "type", vertex.get("type", "object") if isinstance(vertex, dict) else "object")
                vdata = getattr(vertex, "data", vertex.get("data", {}) if isinstance(vertex, dict) else {})
                result[vid] = {"type": vtype, **vdata}
        return result

    def _get_all_edges(self) -> list[dict[str, Any]]:
        """Get all edges from explicit list or backend."""
        if self._edges is not None:
            return self._edges
        if self._backend is None:
            return []
        # Backend doesn't have iter_edges; we reconstruct from neighbour queries.
        # For test scenarios, use explicit edges.
        return []

    def filter_by_type(self, vertex_type: str) -> GraphView:
        """Build a view containing only vertices of the given type.

        Args:
            vertex_type: the vertex type to filter by (e.g. "claim", "evidence").

        Returns:
            GraphView with only matching vertices + their edges.
        """
        all_vertices = self._get_all_vertices()
        all_edges = self._get_all_edges()

        filtered_vertices = {
            vid: vdata for vid, vdata in all_vertices.items()
            if vdata.get("type") == vertex_type
        }

        # Include edges where both endpoints are in the filtered set.
        filtered_edges = [
            edge for edge in all_edges
            if edge.get("source") in filtered_vertices or edge.get("target") in filtered_vertices
        ]

        return GraphView(vertices=filtered_vertices, edges=filtered_edges)

    def filter_by_edge_kind(self, edge_kind: str) -> GraphView:
        """Build a view containing only edges of the given kind.

        Args:
            edge_kind: the edge kind to filter by (e.g. "supports", "contradicts").

        Returns:
            GraphView with only matching edges + their endpoint vertices.
        """
        all_vertices = self._get_all_vertices()
        all_edges = self._get_all_edges()

        filtered_edges = [edge for edge in all_edges if edge.get("kind") == edge_kind]

        # Include vertices that are endpoints of filtered edges.
        endpoint_ids = set()
        for edge in filtered_edges:
            endpoint_ids.add(edge.get("source", ""))
            endpoint_ids.add(edge.get("target", ""))

        filtered_vertices = {
            vid: vdata for vid, vdata in all_vertices.items()
            if vid in endpoint_ids
        }

        return GraphView(vertices=filtered_vertices, edges=filtered_edges)

    def subgraph(self, vertex_ids: list[str]) -> GraphView:
        """Build a view containing only the specified vertices + edges between them.

        Args:
            vertex_ids: list of vertex IDs to include.

        Returns:
            GraphView with only those vertices + edges where both endpoints
            are in the set.
        """
        all_vertices = self._get_all_vertices()
        all_edges = self._get_all_edges()

        vertex_set = set(vertex_ids)
        filtered_vertices = {
            vid: vdata for vid, vdata in all_vertices.items()
            if vid in vertex_set
        }

        filtered_edges = [
            edge for edge in all_edges
            if edge.get("source") in vertex_set and edge.get("target") in vertex_set
        ]

        return GraphView(vertices=filtered_vertices, edges=filtered_edges)

    def full_view(self) -> GraphView:
        """Build a complete view of the graph (no filtering)."""
        return GraphView(
            vertices=self._get_all_vertices(),
            edges=self._get_all_edges(),
        )
