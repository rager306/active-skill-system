"""Tests for M049 S02 — SandboxRunDiff."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.application.test_graph_store_port import InMemoryGraphStore

from active_skill_system.application.use_cases.sandbox_run_diff import (
    SandboxRunDiff,
)
from active_skill_system.domain.loop_graph import (
    LoopEdge,
    LoopEdgeKind,
    LoopVertex,
    LoopVertexKind,
)


def _make_run_with_steps(
    store: InMemoryGraphStore, loop_id: str, step_kinds: list[str],
) -> None:
    """Populate ``store`` with a single loop + given trajectory steps."""
    loop_v = LoopVertex(f"loop:{loop_id}", LoopVertexKind.LOOP, loop_id)
    store.store_vertex(loop_v)
    for i, kind in enumerate(step_kinds):
        step = LoopVertex(
            f"trajectory_step:{loop_id}-{i:03d}",
            LoopVertexKind.TRAJECTORY_STEP, kind,
        )
        store.store_vertex(step)
        store.store_edge(LoopEdge(LoopEdgeKind.USES, f"loop:{loop_id}", step.id))


def test_diff_rejects_none_graph() -> None:
    with pytest.raises(TypeError, match="graph must be a GraphReaderPort"):
        SandboxRunDiff(graph=None)  # type: ignore[arg-type]


def test_diff_returns_missing_id_when_a_unknown() -> None:
    g = InMemoryGraphStore()
    _make_run_with_steps(g, "r1", ["prompt_build", "finish"])
    diff = SandboxRunDiff(graph=g)
    cmp = diff.compare("unknown", "r1")
    assert cmp.missing_id == "loop:unknown"
    assert cmp.loop_a is None
    assert cmp.loop_b is None


def test_diff_returns_missing_id_when_b_unknown() -> None:
    g = InMemoryGraphStore()
    _make_run_with_steps(g, "r1", ["prompt_build", "finish"])
    diff = SandboxRunDiff(graph=g)
    cmp = diff.compare("r1", "ghost")
    assert cmp.missing_id == "loop:ghost"


def test_diff_score_one_vs_one_both_finish() -> None:
    g = InMemoryGraphStore()
    _make_run_with_steps(g, "r1", ["prompt_build", "llm_respond", "verify", "finish"])
    _make_run_with_steps(g, "r2", ["prompt_build", "verify", "finish"])
    diff = SandboxRunDiff(graph=g)
    cmp = diff.compare("r1", "r2")
    assert cmp.missing_id == ""
    assert cmp.loop_a is not None
    assert cmp.loop_b is not None
    assert cmp.loop_a.score == 1.0
    assert cmp.loop_b.score == 1.0
    assert cmp.score_delta == 0.0
    assert cmp.length_delta == -1  # r1=4, r2=3: b-a = -1
    assert "llm_respond" in cmp.kinds_only_in_a
    assert cmp.kinds_only_in_b == ()
    assert "prompt_build" in cmp.kinds_in_both
    assert "finish" in cmp.kinds_in_both


def test_diff_score_zero_when_last_step_is_failure() -> None:
    g = InMemoryGraphStore()
    _make_run_with_steps(g, "r1", ["prompt_build", "verify", "failure"])
    _make_run_with_steps(g, "r2", ["prompt_build", "verify", "finish"])
    diff = SandboxRunDiff(graph=g)
    cmp = diff.compare("r1", "r2")
    assert cmp.loop_a.score == 0.0
    assert cmp.loop_b.score == 1.0
    assert cmp.score_delta == 1.0


def test_diff_handles_already_prefixed_loop_id() -> None:
    g = InMemoryGraphStore()
    _make_run_with_steps(g, "r1", ["finish"])
    _make_run_with_steps(g, "r2", ["finish"])
    diff = SandboxRunDiff(graph=g)
    cmp = diff.compare("loop:r1", "loop:r2")
    assert cmp.missing_id == ""
    assert cmp.loop_a.loop_id == "r1"


def test_diff_models_match_when_same_log_model() -> None:
    g = InMemoryGraphStore()
    _make_run_with_steps(g, "r1", ["finish"])
    _make_run_with_steps(g, "r2", ["finish"])
    tmp = Path("/tmp/diff_log_match.log")
    tmp.write_text(
        "session_start model=minimax/MiniMax-M3 executor=bwrap\n"
        "run_complete run_id=r1 model=minimax/MiniMax-M3 score=1.00\n"
        "session_start model=minimax/MiniMax-M3 executor=bwrap\n"
        "run_complete run_id=r2 model=minimax/MiniMax-M3 score=1.00\n",
        encoding="utf-8",
    )
    diff = SandboxRunDiff(graph=g, log_dir="/tmp")
    cmp = diff.compare("r1", "r2")
    assert cmp.models_match is True
    assert cmp.loop_a.model == "minimax/MiniMax-M3"
    assert cmp.loop_b.model == "minimax/MiniMax-M3"
    tmp.unlink(missing_ok=True)


def test_diff_models_mismatch_when_different() -> None:
    g = InMemoryGraphStore()
    _make_run_with_steps(g, "r1", ["finish"])
    _make_run_with_steps(g, "r2", ["finish"])
    tmp = Path("/tmp/diff_log_mismatch.log")
    tmp.write_text(
        "session_start model=minimax/MiniMax-M3 executor=bwrap\n"
        "run_complete run_id=r1 model=minimax/MiniMax-M3 score=1.00\n"
        "session_start model=glm/glm-5.2 executor=bwrap\n"
        "run_complete run_id=r2 model=glm/glm-5.2 score=1.00\n",
        encoding="utf-8",
    )
    diff = SandboxRunDiff(graph=g, log_dir="/tmp")
    cmp = diff.compare("r1", "r2")
    assert cmp.models_match is False
    assert cmp.loop_a.model == "minimax/MiniMax-M3"
    assert cmp.loop_b.model == "glm/glm-5.2"
    tmp.unlink(missing_ok=True)


def test_diff_models_none_when_no_log_dir() -> None:
    g = InMemoryGraphStore()
    _make_run_with_steps(g, "r1", ["finish"])
    _make_run_with_steps(g, "r2", ["finish"])
    diff = SandboxRunDiff(graph=g)  # no log_dir
    cmp = diff.compare("r1", "r2")
    assert cmp.loop_a.model is None
    assert cmp.models_match is None


def test_diff_summary_human_readable() -> None:
    g = InMemoryGraphStore()
    _make_run_with_steps(g, "r1", ["prompt_build", "verify", "finish"])
    _make_run_with_steps(g, "r2", ["prompt_build", "verify", "failure"])
    diff = SandboxRunDiff(graph=g)
    cmp = diff.compare("r1", "r2")
    s = cmp.summary()
    assert "compare: r1 vs r2" in s
    assert "score:" in s
    assert "length:" in s
    assert "only in A:" in s
    assert "only in B:" in s
    assert "both:" in s


def test_diff_summary_when_missing_id() -> None:
    g = InMemoryGraphStore()
    diff = SandboxRunDiff(graph=g)
    cmp = diff.compare("nope", "also-nope")
    s = cmp.summary()
    assert "not found" in s
    assert "loop:nope" in s
