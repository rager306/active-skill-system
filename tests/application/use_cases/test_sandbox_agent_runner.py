"""Tests for SandboxAgentRunner (M042 S02 T02, refactored M043 S01 T03).

Offline tests use a FakeReasoningEngine returning known source — no real LLM.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from active_skill_system.application.ports.reasoning_engine import (
    ReasoningRequest,
    ReasoningResult,
)
from active_skill_system.application.use_cases.sandbox_agent_runner import (
    SandboxAgentRunner,
    SandboxRunResult,
)
from active_skill_system.domain.loop import LoopState

_GOOD_SOURCE = '''"""Generated cache types."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum


class CacheNodeKind(StrEnum):
    """Node kinds for the cache benchmark."""

    ENTRY = "entry"
    EVICTION = "eviction"
    POLICY = "policy"


@dataclass(frozen=True)
class CacheMetrics:
    """Cache metrics; hit_count is the inverse primary axis (higher is better)."""

    hit_count: int
    miss_count: int
    eviction_count: int
    memory_bytes: int

    def better_than(self, other: "CacheMetrics") -> bool:
        if not isinstance(other, CacheMetrics):
            return False
        if self.hit_count > other.hit_count:
            return True
        if self.hit_count == other.hit_count:
            return self.miss_count < other.miss_count
        return False
'''

_BROKEN_SOURCE = '''"""Broken candidate."""
from dataclasses import dataclass

@dataclass
class CacheMetrics:
    hit_count: int
    size_bytes: int
    def better_than(self, other):
        return self.hit_count < other.hit_count
'''


class _FakeReasoningEngine:
    """Fake reasoning engine returning known source or simulating failure."""

    def __init__(self, *, text: str = _GOOD_SOURCE, fail: bool = False) -> None:
        self._text = text
        self._fail = fail

    def forward(self, request: ReasoningRequest) -> ReasoningResult:
        if self._fail:
            return ReasoningResult(text="", model=request.model, error="ConnectionError: simulated")
        return ReasoningResult(
            text=f"```python\n{self._text}\n```", model="fake/model", finish_reason="end_turn"
        )


# ── Constructor contract ──────────────────────────────────────────────


def test_init_rejects_missing_engine():
    with pytest.raises(TypeError):
        SandboxAgentRunner(engine=None)  # type: ignore[arg-type]


def test_init_rejects_non_engine():
    with pytest.raises(TypeError):
        SandboxAgentRunner(engine="not an engine")  # type: ignore[arg-type]


# ── Happy path ────────────────────────────────────────────────────────


def test_good_source_scores_full(tmp_path: Path):
    runner = SandboxAgentRunner(engine=_FakeReasoningEngine(text=_GOOD_SOURCE), sandbox_dir=tmp_path)
    result = runner.run()
    assert isinstance(result, SandboxRunResult)
    assert result.fitness.score == 1.0
    assert result.loop.state is LoopState.DONE
    assert result.generated_path is not None
    assert Path(result.generated_path).exists()


def test_broken_source_scores_below_one(tmp_path: Path):
    runner = SandboxAgentRunner(engine=_FakeReasoningEngine(text=_BROKEN_SOURCE), sandbox_dir=tmp_path)
    result = runner.run()
    assert result.fitness.score < 1.0
    assert result.loop.state is LoopState.FAILED


def test_engine_error_records_failed_loop(tmp_path: Path):
    runner = SandboxAgentRunner(engine=_FakeReasoningEngine(fail=True), sandbox_dir=tmp_path)
    result = runner.run()
    assert result.loop.state is LoopState.FAILED
    assert result.error is not None
    assert result.fitness.score == 0.0


def test_loop_has_budget_and_lifecycle(tmp_path: Path):
    runner = SandboxAgentRunner(engine=_FakeReasoningEngine(), sandbox_dir=tmp_path)
    result = runner.run()
    assert result.loop.budget.max_llm_calls == 1
    assert len(result.loop.lifecycle) >= 2


def test_prompt_contains_required_fields():
    from active_skill_system.application.use_cases.sandbox_agent_runner import _build_prompt
    prompt = _build_prompt()
    for field in ("hit_count", "miss_count", "eviction_count", "memory_bytes"):
        assert field in prompt
    assert "better_than" in prompt
    assert "higher" in prompt.lower() or "inverse" in prompt.lower()


def test_extract_code_strips_fences():
    from active_skill_system.application.use_cases.sandbox_agent_runner import _extract_code
    assert _extract_code("```python\nx = 1\n```") == "x = 1"
    assert _extract_code("y = 2") == "y = 2"


def test_counter_increments_across_runs(tmp_path: Path):
    runner = SandboxAgentRunner(engine=_FakeReasoningEngine(), sandbox_dir=tmp_path)
    r1 = runner.run()
    r2 = runner.run()
    assert r1.loop.id != r2.loop.id


def test_runner_with_trace_emits_spans() -> None:
    """SandboxAgentRunner with TraceCollector emits agent.run span."""
    from active_skill_system.adapters.inmemory_trace_collector import (
        InMemoryTraceCollector,
    )

    class _FakeEngine:
        def forward(self, request):
            from active_skill_system.application.ports.reasoning_engine import (
                ReasoningResult,
            )
            return ReasoningResult(
                text="```python\nx = 1\n```",
                model=request.model,
                finish_reason="end_turn",
            )

    tc = InMemoryTraceCollector()
    runner = SandboxAgentRunner(
        engine=_FakeEngine(),
        sandbox_dir="runs/sandbox_test_trace",
        trace=tc,
    )
    result = runner.run(model="test-model")
    assert tc.span_count() >= 1
    spans = list(tc.iter_spans())
    ops = [s.operation for s in spans]
    assert "agent.run" in ops
    agent_span = [s for s in spans if s.operation == "agent.run"][0]
    assert agent_span.attributes.get("model") == "test-model"
    assert agent_span.attributes.get("score") == result.fitness.score
