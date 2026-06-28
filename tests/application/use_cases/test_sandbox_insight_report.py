"""Tests for M049 S01 — ReportReader (sandbox insight report)."""

from __future__ import annotations

import pytest
from tests.application.test_graph_store_port import InMemoryGraphStore

from active_skill_system.application.use_cases.sandbox_insight_report import (
    InsightReport,
    ReportReader,
)
from active_skill_system.domain.loop_graph import (
    LoopEdge,
    LoopEdgeKind,
    LoopVertex,
    LoopVertexKind,
)


def _make_loop(loop_id: str, score: float) -> tuple[LoopVertex, ...]:
    """Build a minimal graph with one loop + 3 trajectory steps + 1 skill."""
    loop_v = LoopVertex(f"loop:{loop_id}", LoopVertexKind.LOOP, loop_id)
    skill_v = LoopVertex("skill:sandbox-cache-task", LoopVertexKind.SKILL, "sandbox-cache-task")
    step1 = LoopVertex(
        f"trajectory_step:{loop_id}-000", LoopVertexKind.TRAJECTORY_STEP, "prompt_build",
    )
    step2 = LoopVertex(
        f"trajectory_step:{loop_id}-001", LoopVertexKind.TRAJECTORY_STEP, "llm_respond",
    )
    last_kind = "finish" if score >= 1.0 else "failure"
    step3 = LoopVertex(
        f"trajectory_step:{loop_id}-002", LoopVertexKind.TRAJECTORY_STEP, last_kind,
    )
    return loop_v, skill_v, step1, step2, step3


def test_report_reader_empty_graph_returns_zero_counts() -> None:
    g = InMemoryGraphStore()
    r = ReportReader(graph=g)
    report = r.read()
    assert isinstance(report, InsightReport)
    assert report.total_loops == 0
    assert report.total_vertices == 0
    assert report.total_edges == 0
    assert report.runs_with_score_1 == 0
    assert report.runs_with_score_lt_1 == 0
    assert report.verifier_pass_rate == 0.0
    assert report.trajectory_kinds == {}
    assert report.model_breakdown == {}


def test_report_reader_single_successful_loop() -> None:
    g = InMemoryGraphStore()
    for v in _make_loop("r1", 1.0):
        g.store_vertex(v)
    g.store_edge(LoopEdge(LoopEdgeKind.CREATED, "intent:r1", "loop:r1"))
    g.store_edge(LoopEdge(LoopEdgeKind.USES, "loop:r1", "skill:sandbox-cache-task"))
    g.store_edge(LoopEdge(LoopEdgeKind.USES, "loop:r1", "trajectory_step:r1-000"))
    g.store_edge(LoopEdge(LoopEdgeKind.USES, "loop:r1", "trajectory_step:r1-001"))
    g.store_edge(LoopEdge(LoopEdgeKind.USES, "loop:r1", "trajectory_step:r1-002"))

    r = ReportReader(graph=g)
    report = r.read()
    assert report.total_loops == 1
    assert report.total_vertices == 5
    assert report.runs_with_score_1 == 1
    assert report.runs_with_score_lt_1 == 0
    assert report.verifier_pass_rate == 1.0
    assert report.trajectory_kinds == {"prompt_build": 1, "llm_respond": 1, "finish": 1}
    assert report.skill_usage == {"sandbox-cache-task": 1}
    assert report.created_edges == 1


def test_report_reader_failed_loop_increments_lt_1() -> None:
    g = InMemoryGraphStore()
    for v in _make_loop("r2", 0.3):
        g.store_vertex(v)
    g.store_edge(LoopEdge(LoopEdgeKind.CREATED, "intent:r2", "loop:r2"))
    g.store_edge(LoopEdge(LoopEdgeKind.USES, "loop:r2", "skill:sandbox-cache-task"))
    g.store_edge(LoopEdge(LoopEdgeKind.USES, "loop:r2", "trajectory_step:r2-000"))
    g.store_edge(LoopEdge(LoopEdgeKind.USES, "loop:r2", "trajectory_step:r2-001"))
    g.store_edge(LoopEdge(LoopEdgeKind.USES, "loop:r2", "trajectory_step:r2-002"))

    r = ReportReader(graph=g)
    report = r.read()
    assert report.runs_with_score_1 == 0
    assert report.runs_with_score_lt_1 == 1
    assert report.verifier_pass_rate == 0.0
    assert report.executor_failures == 1
    assert report.trajectory_kinds.get("failure") == 1


def test_report_reader_multi_loop_pass_rate() -> None:
    g = InMemoryGraphStore()
    for loop_id, score in [("r1", 1.0), ("r2", 0.5), ("r3", 1.0)]:
        for v in _make_loop(loop_id, score):
            g.store_vertex(v)
        g.store_edge(LoopEdge(LoopEdgeKind.USES, f"loop:{loop_id}", "skill:sandbox-cache-task"))
        for i in range(3):
            g.store_edge(LoopEdge(
                LoopEdgeKind.USES, f"loop:{loop_id}",
                f"trajectory_step:{loop_id}-00{i}",
            ))
    r = ReportReader(graph=g)
    report = r.read()
    assert report.total_loops == 3
    assert report.runs_with_score_1 == 2
    assert report.runs_with_score_lt_1 == 1
    assert abs(report.verifier_pass_rate - (2 / 3)) < 1e-9


def test_report_reader_rejects_none_graph() -> None:
    with pytest.raises(TypeError, match="graph must be a GraphReaderPort"):
        ReportReader(graph=None)  # type: ignore[arg-type]


def test_report_reader_with_ratchet_counts_entries() -> None:
    g = InMemoryGraphStore()

    class _FakeRatchet:
        @property
        def entries(self) -> tuple:
            return ("a", "b", "c")

    r = ReportReader(graph=g, ratchet=_FakeRatchet())
    report = r.read()
    assert report.ratchet_entries == 3


def test_report_reader_without_ratchet_is_zero() -> None:
    g = InMemoryGraphStore()
    r = ReportReader(graph=g)
    assert r.read().ratchet_entries == 0


def test_report_reader_facts_returns_ordered_pairs() -> None:
    g = InMemoryGraphStore()
    r = ReportReader(graph=g)
    facts = r.read().facts()
    assert isinstance(facts, tuple)
    assert facts[0][0] == "total_loops"
    assert facts[-1][0] == "ratchet_entries"
    # 14 facts total.
    assert len(facts) == 14
