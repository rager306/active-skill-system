"""Tests for SandboxHarness (M042 S03 T02)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from active_skill_system.application.use_cases.sandbox_agent_runner import SandboxRunResult
from active_skill_system.application.use_cases.sandbox_harness import (
    ComparativeReport,
    SandboxHarness,
)
from active_skill_system.application.use_cases.sandbox_verifier import SandboxFitness
from active_skill_system.domain.loop import Budget, Loop

_GOOD = "good"
_BROKEN = "broken"


class _FakeReasoningEngine:
    """Returns different source quality based on the model name requested."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def forward(self, request) -> Any:  # noqa: ANN001
        from active_skill_system.application.ports.reasoning_engine import ReasoningResult

        self.calls.append(request.model)
        if "good" in request.model:
            text = "```python\n" + _good_source() + "\n```"
        elif "fail" in request.model:
            return ReasoningResult(text="", model=request.model, error="ConnectionError: down")
        else:
            text = "```python\n" + _broken_source() + "\n```"
        return ReasoningResult(text=text, model=request.model, finish_reason="end_turn")


def _good_source() -> str:
    return (
        '"""Good."""\n'
        "from dataclasses import dataclass\n"
        "from enum import StrEnum\n\n\n"
        'class CacheNodeKind(StrEnum):\n    """Kinds."""\n\n'
        '    ENTRY = "entry"\n    EVICTION = "eviction"\n    POLICY = "policy"\n\n\n'
        "@dataclass(frozen=True)\n"
        'class CacheMetrics:\n    """Metrics; hit_count higher=better."""\n\n'
        "    hit_count: int\n    miss_count: int\n"
        "    eviction_count: int\n    memory_bytes: int\n\n"
        "    def better_than(self, other):\n"
        "        if self.hit_count > other.hit_count:\n            return True\n"
        "        if self.hit_count == other.hit_count:\n"
        "            return self.miss_count < other.miss_count\n"
        "        return False\n"
    )


def _broken_source() -> str:
    return (
        "from dataclasses import dataclass\n\n"
        "@dataclass\nclass CacheMetrics:\n"
        "    hit_count: int\n    size_bytes: int\n"
    )


def _make_loop(state: str = "done") -> Loop:

    # Use Loop.start to get a valid lifecycle (STARTED → RUNNING), then the
    # test doesn't depend on the state invariant for empty lifecycle.
    loop = Loop.start(id=f"loop-{state}", intent="x", budget=Budget(max_llm_calls=1))
    return loop


# ── Constructor ───────────────────────────────────────────────────────


def test_init_rejects_missing_engine():
    with pytest.raises(TypeError):
        SandboxHarness(engine=None, models=["a"])  # type: ignore[arg-type]


def test_init_rejects_empty_models():
    with pytest.raises(ValueError):
        SandboxHarness(engine=_FakeReasoningEngine(), models=[])


# ── Multi-model run ───────────────────────────────────────────────────


def test_two_models_comparative_report(tmp_path: Path):
    harness = SandboxHarness(
        engine=_FakeReasoningEngine(),
        models=["minimax/good", "glm/broken"],
        sandbox_dir=tmp_path,
    )
    report = harness.run_all()
    assert isinstance(report, ComparativeReport)
    assert len(report.entries) == 2
    assert report.winner_model == "minimax/good"
    assert report.winner_score == 1.0
    assert "minimax/good" in report.reader_query_answer


def test_model_failure_does_not_abort(tmp_path: Path):
    """A provider error is caught by the runner (→ FAILED Loop entry), not aborting."""
    harness = SandboxHarness(
        engine=_FakeReasoningEngine(),
        models=["minimax/good", "fake/fail", "glm/broken"],
        sandbox_dir=tmp_path,
    )
    report = harness.run_all()
    # All 3 models produce entries: good→DONE, fail→FAILED (caught by runner), broken→FAILED.
    assert len(report.entries) == 3
    failed = [e for e in report.entries if e.loop_state == "failed"]
    assert len(failed) >= 1
    assert report.winner_model == "minimax/good"


def test_winner_tie_break_by_loc(tmp_path: Path):
    """When two models score equally, the one with lower loc wins."""
    harness = SandboxHarness(
        engine=_FakeReasoningEngine(),
        models=["aaa/good", "zzz/good"],
        sandbox_dir=tmp_path,
    )
    report = harness.run_all()
    # Both score 1.0; tie-break loc (same) → alphabetical → aaa wins.
    assert report.winner_model == "aaa/good"


def test_no_perfect_score_reader_answer(tmp_path: Path):
    harness = SandboxHarness(
        engine=_FakeReasoningEngine(),
        models=["glm/broken"],
        sandbox_dir=tmp_path,
    )
    report = harness.run_all()
    assert report.winner_score < 1.0
    assert "best:" in report.reader_query_answer


def test_table_renders():
    entry_results = [
        SandboxRunResult(
            loop=_make_loop(),
            fitness=SandboxFitness(
                structure_ok=True, invariants_ok=True, ranking_ok=True, ruff_clean=True
            ),
            model="test/model",
        )
    ]
    from active_skill_system.application.use_cases.sandbox_harness import SandboxHarness as H

    report = H._build_report(H, entry_results)  # type: ignore[arg-type]
    table = report.table()
    assert "test/model" in table
    assert "winner" in table
    assert "reader query" in table
