"""Tests for LadybugGraphStore adapter (RGLA, D010).

Runs the shared GraphStore conformance harness (from test_graph_store_port)
plus LadybugDB-specific idempotency, neighbour-direction, and round-trip tests,
and an AST guard that ``ladybug`` is imported only in the adapter module.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from tests._graph_store_conformance import run_graph_store_conformance

from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore
from active_skill_system.application.ports.graph_store import GraphStore
from active_skill_system.domain.loop import Budget, Loop, LoopEvent, LoopEventKind, LoopState
from active_skill_system.domain.loop_graph import (
    LoopEdge,
    LoopEdgeKind,
    LoopGraph,
    LoopVertex,
    LoopVertexKind,
    project,
)

# ── Shared contract ───────────────────────────────────────────────────


def test_ladybug_store_is_a_graph_store():
    assert isinstance(LadybugGraphStore(":memory:"), GraphStore)


def test_ladybug_store_satisfies_conformance():
    store = LadybugGraphStore(":memory:")
    run_graph_store_conformance(store)


# ── LadybugDB-specific ────────────────────────────────────────────────


def test_idempotent_store_loop_graph_no_duplicates():
    store = LadybugGraphStore(":memory:")
    g = LoopGraph(
        vertices=(
            LoopVertex(id="loop:1", kind=LoopVertexKind.LOOP),
            LoopVertex(id="skill:s1", kind=LoopVertexKind.SKILL),
            LoopVertex(id="verifier:v1", kind=LoopVertexKind.VERIFIER),
        ),
        edges=(
            LoopEdge(LoopEdgeKind.USES, "loop:1", "skill:s1"),
            LoopEdge(LoopEdgeKind.VERIFIED_BY, "loop:1", "verifier:v1"),
        ),
    )
    store.store_loop_graph(g)
    store.store_loop_graph(g)
    assert store.count_vertices() == 3
    assert store.count_edges() == 2


def test_query_neighbours_out_in_both_on_chain():
    store = LadybugGraphStore(":memory:")
    # a -> b -> c
    vs = (
        LoopVertex(id="a", kind=LoopVertexKind.LOOP),
        LoopVertex(id="b", kind=LoopVertexKind.SKILL),
        LoopVertex(id="c", kind=LoopVertexKind.VERIFIER),
    )
    es = (LoopEdge(LoopEdgeKind.USES, "a", "b"), LoopEdge(LoopEdgeKind.USES, "b", "c"))
    store.store_loop_graph(LoopGraph(vertices=vs, edges=es))
    assert {v.id for v in store.query_neighbours("a", direction="out")} == {"b"}
    assert {v.id for v in store.query_neighbours("c", direction="in")} == {"b"}
    assert {v.id for v in store.query_neighbours("b", direction="both")} == {"a", "c"}


def test_has_edge_by_kind():
    store = LadybugGraphStore(":memory:")
    store.store_loop_graph(
        LoopGraph(
            vertices=(
                LoopVertex(id="loop:1", kind=LoopVertexKind.LOOP),
                LoopVertex(id="skill:s1", kind=LoopVertexKind.SKILL),
            ),
            edges=(LoopEdge(LoopEdgeKind.USES, "loop:1", "skill:s1"),),
        )
    )
    assert store.has_edge(LoopEdgeKind.USES, "loop:1", "skill:s1")
    assert not store.has_edge(LoopEdgeKind.FIXES, "loop:1", "skill:s1")


def test_get_vertex_returns_typed_vertex():
    store = LadybugGraphStore(":memory:")
    store.store_vertex(LoopVertex(id="loop:1", kind=LoopVertexKind.LOOP, label="L1"))
    v = store.get_vertex("loop:1")
    assert v is not None
    assert v.kind is LoopVertexKind.LOOP
    assert v.label == "L1"
    assert store.get_vertex("missing") is None


def test_counts_after_mixed_stores():
    store = LadybugGraphStore(":memory:")
    store.store_vertex(LoopVertex(id="a", kind=LoopVertexKind.LOOP))
    store.store_vertex(LoopVertex(id="b", kind=LoopVertexKind.SKILL))
    store.store_vertex(LoopVertex(id="b", kind=LoopVertexKind.SKILL))  # dup -> upsert
    store.store_edge(LoopEdge(LoopEdgeKind.USES, "a", "b"))
    assert store.count_vertices() == 2
    assert store.count_edges() == 1


# ── Round-trip through project() ──────────────────────────────────────


def test_projected_loop_round_trips_and_finds_uses_skill():
    store = LadybugGraphStore(":memory:")
    loop = Loop.start("loop-1", "optimize sql", Budget(max_iterations=5), skills=("sql-plan-opt",))
    loop = loop.advance(
        LoopEvent.now(LoopEventKind.VERIFIED, LoopState.VERIFYING, {"verifier": "gap-detector"})
    )
    store.store_loop_graph(project(loop))
    neighbours = store.query_neighbours("loop:loop-1", direction="out")
    ids = {v.id for v in neighbours}
    assert "skill:sql-plan-opt" in ids
    assert store.has_edge(LoopEdgeKind.VERIFIED_BY, "loop:loop-1", "verifier:gap-detector")


# ── AST guard: ladybug confined to the adapter ───────────────────────


def _module_asts() -> list[tuple[Path, ast.AST]]:
    root = Path("src/active_skill_system")
    return [
        (py, ast.parse(py.read_text(encoding="utf-8")))
        for py in root.rglob("*.py")
        if "__pycache__" not in py.parts
    ]


def _imports(tree: ast.AST, pkg: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name == pkg for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and (node.module or "") == pkg:
            return True
    return False


def test_ladybug_not_imported_in_domain_or_application():
    offenders = []
    for py, tree in _module_asts():
        rel = py.relative_to(Path("src/active_skill_system"))
        if rel.parts and rel.parts[0] in ("domain", "application") and _imports(tree, "ladybug"):
            offenders.append(str(rel))
    assert not offenders, f"ladybug imported in domain/application: {offenders}"


def test_ladybug_only_in_adapter_module():
    offenders = []
    for py, tree in _module_asts():
        rel = str(py.relative_to(Path("src/active_skill_system")))
        if rel == "adapters/ladybug_graph_store.py":
            continue
        if _imports(tree, "ladybug"):
            offenders.append(rel)
    assert not offenders, f"ladybug imported outside the adapter: {offenders}"


def test_rejects_empty_path():
    with pytest.raises(ValueError):
        LadybugGraphStore(path="")
