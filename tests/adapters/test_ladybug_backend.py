"""Tests for M051 S01 — generic graph primitives + GraphBackend port."""

from __future__ import annotations

import pytest

from active_skill_system.application.ports.graph_backend import GraphBackend
from active_skill_system.domain.graph_primitives import (
    Edge,
    GraphEvent,
    GraphEventType,
    Vertex,
)

# ── Domain primitives ────────────────────────────────────────────────


def test_vertex_post_init_rejects_empty_id() -> None:
    with pytest.raises(ValueError, match="id must be a non-empty"):
        Vertex(id="", type="loop")


def test_vertex_post_init_rejects_empty_type() -> None:
    with pytest.raises(ValueError, match="type must be a non-empty"):
        Vertex(id="x", type="")


def test_vertex_post_init_rejects_non_dict_data() -> None:
    with pytest.raises(ValueError, match="data must be a dict"):
        Vertex(id="x", type="t", data="not-a-dict")  # type: ignore[arg-type]


def test_vertex_accepts_empty_data() -> None:
    v = Vertex(id="x", type="t")
    assert v.data == {}


def test_edge_post_init_rejects_empty_kind() -> None:
    with pytest.raises(ValueError, match="kind must be a non-empty"):
        Edge(kind="", src="a", dst="b")


def test_edge_post_init_rejects_empty_src() -> None:
    with pytest.raises(ValueError, match="src must be a non-empty"):
        Edge(kind="uses", src="", dst="b")


def test_edge_post_init_rejects_empty_dst() -> None:
    with pytest.raises(ValueError, match="dst must be a non-empty"):
        Edge(kind="uses", src="a", dst="")


def test_graph_event_post_init_rejects_empty_id() -> None:
    with pytest.raises(ValueError, match="id must be a non-empty"):
        GraphEvent(id="", type="object.created")


def test_graph_event_post_init_rejects_empty_type() -> None:
    with pytest.raises(ValueError, match="type must be a non-empty"):
        GraphEvent(id="x", type="")


def test_graph_event_now_auto_generates_id_and_timestamp() -> None:
    e = GraphEvent.now("object.created", payload={"k": 1}, actor="test")
    assert e.id.startswith("evt-")
    assert e.type == "object.created"
    assert e.payload == {"k": 1}
    assert e.actor == "test"
    assert e.timestamp_ns > 0


def test_graph_event_now_accepts_explicit_id() -> None:
    e = GraphEvent.now("x", event_id="custom-id")
    assert e.id == "custom-id"


def test_graph_event_type_constants_exist() -> None:
    assert GraphEventType.OBJECT_CREATED == "object.created"
    assert GraphEventType.BEHAVIOR_FAILED == "behavior.failed"
    assert GraphEventType.LLM_RESPONDED == "llm.responded"


# ── GraphBackend Protocol structural check ───────────────────────────


def test_graph_backend_is_protocol() -> None:
    from active_skill_system.adapters.ladybug_backend import LadybugBackend

    assert isinstance(LadybugBackend(), GraphBackend)


# ── LadybugBackend functional tests ──────────────────────────────────


def test_ladybug_backend_upsert_and_get_vertex() -> None:
    from active_skill_system.adapters.ladybug_backend import LadybugBackend

    b = LadybugBackend(":memory:")
    v = Vertex(id="claim:1", type="claim", data={"text": "hello"})
    b.upsert_vertex(v)
    got = b.get_vertex("claim:1")
    assert got is not None
    assert got.id == "claim:1"
    assert got.type == "claim"
    assert got.data == {"text": "hello"}


def test_ladybug_backend_get_vertex_missing_returns_none() -> None:
    from active_skill_system.adapters.ladybug_backend import LadybugBackend

    b = LadybugBackend(":memory:")
    assert b.get_vertex("nope") is None


def test_ladybug_backend_upsert_is_idempotent() -> None:
    from active_skill_system.adapters.ladybug_backend import LadybugBackend

    b = LadybugBackend(":memory:")
    v = Vertex(id="x", type="t", data={"a": 1})
    b.upsert_vertex(v)
    b.upsert_vertex(v)
    assert b.count_vertices() == 1


def test_ladybug_backend_upsert_and_has_edge() -> None:
    from active_skill_system.adapters.ladybug_backend import LadybugBackend

    b = LadybugBackend(":memory:")
    b.upsert_vertex(Vertex(id="a", type="t"))
    b.upsert_vertex(Vertex(id="b", type="t"))
    e = Edge(kind="uses", src="a", dst="b", data={"w": 2})
    b.upsert_edge(e)
    assert b.has_edge("uses", "a", "b") is True
    assert b.has_edge("uses", "b", "a") is False


def test_ladybug_backend_neighbours_out() -> None:
    from active_skill_system.adapters.ladybug_backend import LadybugBackend

    b = LadybugBackend(":memory:")
    b.upsert_vertex(Vertex(id="a", type="t"))
    b.upsert_vertex(Vertex(id="b", type="t"))
    b.upsert_vertex(Vertex(id="c", type="t"))
    b.upsert_edge(Edge(kind="uses", src="a", dst="b"))
    b.upsert_edge(Edge(kind="uses", src="a", dst="c"))
    ns = b.neighbours("a", direction="out")
    ids = {n.id for n in ns}
    assert ids == {"b", "c"}


def test_ladybug_backend_count_edges_of_kind() -> None:
    from active_skill_system.adapters.ladybug_backend import LadybugBackend

    b = LadybugBackend(":memory:")
    b.upsert_vertex(Vertex(id="a", type="t"))
    b.upsert_vertex(Vertex(id="b", type="t"))
    b.upsert_vertex(Vertex(id="c", type="t"))
    b.upsert_edge(Edge(kind="uses", src="a", dst="b"))
    b.upsert_edge(Edge(kind="uses", src="a", dst="c"))
    b.upsert_edge(Edge(kind="verified_by", src="a", dst="b"))
    assert b.count_edges_of_kind("uses") == 2
    assert b.count_edges_of_kind("verified_by") == 1
    assert b.count_edges_of_kind("nonexistent") == 0


def test_ladybug_backend_all_vertex_ids() -> None:
    from active_skill_system.adapters.ladybug_backend import LadybugBackend

    b = LadybugBackend(":memory:")
    b.upsert_vertex(Vertex(id="a", type="t"))
    b.upsert_vertex(Vertex(id="b", type="t"))
    ids = set(b.all_vertex_ids())
    assert ids == {"a", "b"}
