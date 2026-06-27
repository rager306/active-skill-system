"""Tests for the GraphStore port contract (RGLA, D010).

Defines the conformance contract any GraphStore adapter must satisfy, and a
minimal in-memory reference implementation used to validate the contract here.
Adapters (e.g. LadybugGraphStore) are tested against the same contract via
``run_graph_store_conformance``.
"""

from __future__ import annotations

from active_skill_system.application.ports.graph_store import GraphStore
from active_skill_system.domain.loop_graph import (
    LoopEdge,
    LoopEdgeKind,
    LoopGraph,
    LoopVertex,
    LoopVertexKind,
)


class InMemoryGraphStore:
    """Minimal in-memory GraphStore reference (R002-clean, stdlib only)."""

    def __init__(self) -> None:
        self._vertices: dict[str, LoopVertex] = {}
        self._edges: dict[tuple[str, str, str], LoopEdge] = {}

    def store_loop_graph(self, graph: LoopGraph) -> None:
        for v in graph.vertices:
            self.store_vertex(v)
        for e in graph.edges:
            self.store_edge(e)

    def store_vertex(self, vertex: LoopVertex) -> None:
        self._vertices[vertex.id] = vertex

    def store_edge(self, edge: LoopEdge) -> None:
        self._edges[(edge.kind.value, edge.src, edge.dst)] = edge

    def get_vertex(self, vertex_id: str) -> LoopVertex | None:
        return self._vertices.get(vertex_id)

    def query_neighbours(self, vertex_id: str, *, direction: str = "out") -> tuple[LoopVertex, ...]:
        if direction == "out":
            ids = {e.dst for e in self._edges.values() if e.src == vertex_id}
        elif direction == "in":
            ids = {e.src for e in self._edges.values() if e.dst == vertex_id}
        else:
            ids = {e.dst for e in self._edges.values() if e.src == vertex_id} | {
                e.src for e in self._edges.values() if e.dst == vertex_id
            }
        return tuple(self._vertices[i] for i in ids if i in self._vertices)

    def has_edge(self, kind: object, src: str, dst: str) -> bool:
        k = kind.value if hasattr(kind, "value") else str(kind)
        return (k, src, dst) in self._edges

    def count_vertices(self) -> int:
        return len(self._vertices)

    def count_edges(self) -> int:
        return len(self._edges)


def _sample_graph() -> LoopGraph:
    loop_v = LoopVertex(id="loop:1", kind=LoopVertexKind.LOOP, label="L1")
    skill_v = LoopVertex(id="skill:s1", kind=LoopVertexKind.SKILL, label="S1")
    edge = LoopEdge(LoopEdgeKind.USES, "loop:1", "skill:s1")
    return LoopGraph(vertices=(loop_v, skill_v), edges=(edge,))


def run_graph_store_conformance(store: GraphStore) -> None:
    """Assert ``store`` satisfies the GraphStore contract.

    Shared by InMemoryGraphStore here and adapter tests elsewhere.
    """
    graph = _sample_graph()

    # store_loop_graph is idempotent.
    store.store_loop_graph(graph)
    store.store_loop_graph(graph)
    assert store.count_vertices() == 2
    assert store.count_edges() == 1

    # get_vertex.
    assert store.get_vertex("loop:1") is not None
    assert store.get_vertex("nope") is None

    # has_edge.
    assert store.has_edge(LoopEdgeKind.USES, "loop:1", "skill:s1")
    assert not store.has_edge(LoopEdgeKind.FIXES, "loop:1", "skill:s1")

    # query_neighbours.
    out = store.query_neighbours("loop:1", direction="out")
    assert any(v.id == "skill:s1" for v in out)
    inn = store.query_neighbours("skill:s1", direction="in")
    assert any(v.id == "loop:1" for v in inn)


# ── Tests against the reference implementation ────────────────────────


def test_inmemory_store_satisfies_contract():
    run_graph_store_conformance(InMemoryGraphStore())


def test_graph_store_is_a_protocol():
    """The port is a runtime_checkable Protocol; the impl satisfies it."""
    assert isinstance(InMemoryGraphStore(), GraphStore)


def test_store_vertex_upsert_is_idempotent():
    store = InMemoryGraphStore()
    v = LoopVertex(id="loop:2", kind=LoopVertexKind.LOOP)
    store.store_vertex(v)
    store.store_vertex(v)
    assert store.count_vertices() == 1


def test_store_edge_upsert_is_idempotent():
    store = InMemoryGraphStore()
    store.store_vertex(LoopVertex(id="loop:3", kind=LoopVertexKind.LOOP))
    store.store_vertex(LoopVertex(id="skill:s2", kind=LoopVertexKind.SKILL))
    e = LoopEdge(LoopEdgeKind.USES, "loop:3", "skill:s2")
    store.store_edge(e)
    store.store_edge(e)
    assert store.count_edges() == 1
