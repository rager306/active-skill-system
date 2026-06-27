"""Shared GraphStore conformance harness (RGLA, D010).

Imported by both the reference-impl test (InMemoryGraphStore) and adapter
tests (LadybugGraphStore) so every GraphStore is validated against the same
contract.
"""

from __future__ import annotations

from active_skill_system.domain.loop_graph import (
    LoopEdge,
    LoopEdgeKind,
    LoopGraph,
    LoopVertex,
    LoopVertexKind,
)


def run_graph_store_conformance(store) -> None:  # noqa: ANN001
    """Assert ``store`` satisfies the GraphStore contract."""
    graph = _sample_graph()

    store.store_loop_graph(graph)
    store.store_loop_graph(graph)
    assert store.count_vertices() == 2
    assert store.count_edges() == 1

    assert store.get_vertex("loop:1") is not None
    assert store.get_vertex("nope") is None

    assert store.has_edge(LoopEdgeKind.USES, "loop:1", "skill:s1")
    assert not store.has_edge(LoopEdgeKind.FIXES, "loop:1", "skill:s1")

    out = store.query_neighbours("loop:1", direction="out")
    assert any(v.id == "skill:s1" for v in out)
    inn = store.query_neighbours("skill:s1", direction="in")
    assert any(v.id == "loop:1" for v in inn)


def _sample_graph() -> LoopGraph:
    return LoopGraph(
        vertices=(
            LoopVertex(id="loop:1", kind=LoopVertexKind.LOOP, label="L1"),
            LoopVertex(id="skill:s1", kind=LoopVertexKind.SKILL, label="S1"),
        ),
        edges=(LoopEdge(LoopEdgeKind.USES, "loop:1", "skill:s1"),),
    )
