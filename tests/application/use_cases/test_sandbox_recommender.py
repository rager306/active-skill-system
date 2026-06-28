"""Tests for M049 S03 — SandboxRecommender."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.application.test_graph_store_port import InMemoryGraphStore

from active_skill_system.application.use_cases.sandbox_recommender import (
    Recommendation,
    SandboxRecommender,
)
from active_skill_system.domain.loop_graph import (
    LoopEdge,
    LoopEdgeKind,
    LoopVertex,
    LoopVertexKind,
)


def _make_run(store: InMemoryGraphStore, loop_id: str, step_kinds: list[str]) -> None:
    store.store_vertex(LoopVertex(f"loop:{loop_id}", LoopVertexKind.LOOP, loop_id))
    for i, kind in enumerate(step_kinds):
        step = LoopVertex(
            f"trajectory_step:{loop_id}-{i:03d}",
            LoopVertexKind.TRAJECTORY_STEP, kind,
        )
        store.store_vertex(step)
        store.store_edge(LoopEdge(LoopEdgeKind.USES, f"loop:{loop_id}", step.id))


def test_recommender_rejects_none_graph() -> None:
    with pytest.raises(TypeError, match="graph must be a GraphReaderPort"):
        SandboxRecommender(graph=None)  # type: ignore[arg-type]


def test_recommender_empty_graph_returns_no_data() -> None:
    g = InMemoryGraphStore()
    rec = SandboxRecommender(graph=g).recommend()
    assert len(rec) == 1
    assert rec[0].kind == "no_data"
    assert rec[0].confidence == "high"


def test_recommender_single_success_no_log_no_model_returns_no_model_recs() -> None:
    g = InMemoryGraphStore()
    _make_run(g, "r1", ["prompt_build", "llm_respond", "verify", "finish"])
    rec = SandboxRecommender(graph=g).recommend()
    # Without log dir, no model data; rules that need model won't fire.
    # All runs passed, no failure, no model → at minimum no_data false,
    # but no model_stable/undertested_model. trajectory_uniform might fire.
    kinds = [r.kind for r in rec]
    assert "no_data" not in kinds
    assert "failed_run_present" not in kinds
    assert "executor_gate_safe" in kinds
    assert "trajectory_uniform" in kinds


def test_recommender_model_stable_when_all_pass_one_model() -> None:
    g = InMemoryGraphStore()
    _make_run(g, "r1", ["prompt_build", "verify", "finish"])
    _make_run(g, "r2", ["prompt_build", "verify", "finish"])
    tmp = Path("/tmp/rec_log_stable.log")
    tmp.write_text(
        "session_start model=minimax/MiniMax-M3 executor=bwrap\n"
        "run_complete run_id=r1 model=minimax/MiniMax-M3 score=1.00\n"
        "session_start model=minimax/MiniMax-M3 executor=bwrap\n"
        "run_complete run_id=r2 model=minimax/MiniMax-M3 score=1.00\n",
        encoding="utf-8",
    )
    rec = SandboxRecommender(graph=g, log_dir="/tmp").recommend()
    kinds = [r.kind for r in rec]
    assert "model_stable" in kinds
    # And undertested_model should fire too (only 1 model tested).
    assert "undertested_model" in kinds
    tmp.unlink(missing_ok=True)


def test_recommender_failed_run_emits_ratchet_suggestion() -> None:
    g = InMemoryGraphStore()
    _make_run(g, "r1", ["prompt_build", "verify", "failure"])
    _make_run(g, "r2", ["prompt_build", "verify", "finish"])
    rec = SandboxRecommender(graph=g).recommend()
    kinds = [r.kind for r in rec]
    assert "failed_run_present" in kinds
    # executor_gate_safe should NOT fire (we have a failure).
    assert "executor_gate_safe" not in kinds


def test_recommender_trajectory_drift_when_varied() -> None:
    g = InMemoryGraphStore()
    _make_run(g, "r1", ["prompt_build", "verify", "finish"])
    _make_run(g, "r2", ["prompt_build", "verify", "verify", "finish"])  # extra verify
    rec = SandboxRecommender(graph=g).recommend()
    kinds = [r.kind for r in rec]
    assert "trajectory_uniform" not in kinds
    assert "trajectory_drift" in kinds


def test_recommender_with_ratchet_counts_in_message() -> None:
    g = InMemoryGraphStore()
    _make_run(g, "r1", ["prompt_build", "verify", "failure"])

    class _FakeRatchet:
        @property
        def entries(self) -> tuple:
            return ("x", "y")

    rec = SandboxRecommender(graph=g, ratchet=_FakeRatchet()).recommend()
    failed = [r for r in rec if r.kind == "failed_run_present"][0]
    assert "2 entries" in failed.message


def test_recommender_sorted_by_confidence() -> None:
    g = InMemoryGraphStore()
    _make_run(g, "r1", ["prompt_build", "verify", "failure"])
    rec = SandboxRecommender(graph=g).recommend()
    order = {"high": 0, "medium": 1, "low": 2}
    confidences = [r.confidence for r in rec]
    indices = [order[c] for c in confidences]
    assert indices == sorted(indices)


def test_recommender_recommendation_to_dict() -> None:
    rec = Recommendation(
        kind="test", message="hello", confidence="high",
        evidence_refs=("a", "b"),
    )
    d = rec.to_dict()
    assert d["kind"] == "test"
    assert d["message"] == "hello"
    assert d["confidence"] == "high"
    assert d["evidence_refs"] == ["a", "b"]


def test_recommender_all_fail_fires_all_fail_rec() -> None:
    g = InMemoryGraphStore()
    _make_run(g, "r1", ["prompt_build", "verify", "failure"])
    _make_run(g, "r2", ["prompt_build", "verify", "failure"])
    rec = SandboxRecommender(graph=g).recommend()
    kinds = [r.kind for r in rec]
    assert "all_fail" in kinds
