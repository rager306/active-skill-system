"""Tests for SandboxAgentRunner (M042 S02 T02).

Offline tests use a FakeProvider returning known source — no real LLM.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from active_skill_system.application.use_cases.sandbox_agent_runner import (
    SandboxAgentRunner,
    SandboxRunResult,
)
from active_skill_system.domain.loop import LoopState

# The full-mark candidate source (matches tests/fixtures/sandbox/cache_full.py).
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
    size_bytes: int  # wrong field name
    def better_than(self, other):
        return self.hit_count < other.hit_count  # wrong direction
'''


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.raw_text = text


class _FakeProvider:
    def __init__(self, *, text: str = _GOOD_SOURCE, fail: bool = False) -> None:
        self.default_model = "fake/model"
        self._text = text
        self._fail = fail

    def complete(self, **kwargs):  # noqa: ANN003
        if self._fail:
            raise ConnectionError("simulated provider down")
        return _FakeResponse(f"```python\n{self._text}\n```")


# ── Constructor contract ──────────────────────────────────────────────


def test_init_rejects_missing_provider():
    with pytest.raises(TypeError):
        SandboxAgentRunner(provider=None)  # type: ignore[arg-type]


def test_init_rejects_non_provider():
    with pytest.raises(TypeError):
        SandboxAgentRunner(provider="not a provider")  # type: ignore[arg-type]


# ── Happy path ────────────────────────────────────────────────────────


def test_good_source_scores_full(tmp_path: Path):
    runner = SandboxAgentRunner(provider=_FakeProvider(text=_GOOD_SOURCE), sandbox_dir=tmp_path)
    result = runner.run()
    assert isinstance(result, SandboxRunResult)
    assert result.fitness.score == 1.0
    assert result.loop.state is LoopState.DONE
    assert result.generated_path is not None
    assert Path(result.generated_path).exists()


def test_broken_source_scores_below_one(tmp_path: Path):
    runner = SandboxAgentRunner(provider=_FakeProvider(text=_BROKEN_SOURCE), sandbox_dir=tmp_path)
    result = runner.run()
    assert result.fitness.score < 1.0
    assert result.loop.state is LoopState.FAILED


def test_provider_error_records_failed_loop(tmp_path: Path):
    runner = SandboxAgentRunner(provider=_FakeProvider(fail=True), sandbox_dir=tmp_path)
    result = runner.run()
    assert result.loop.state is LoopState.FAILED
    assert result.error is not None
    assert result.fitness.score == 0.0


def test_loop_has_budget_and_lifecycle(tmp_path: Path):
    runner = SandboxAgentRunner(provider=_FakeProvider(), sandbox_dir=tmp_path)
    result = runner.run()
    assert result.loop.budget.max_llm_calls == 1
    assert len(result.loop.lifecycle) >= 2  # STARTED + FINISHED/FAILED


def test_prompt_contains_required_fields():
    from active_skill_system.application.use_cases.sandbox_agent_runner import _build_prompt
    prompt = _build_prompt()
    for field in ("hit_count", "miss_count", "eviction_count", "memory_bytes"):
        assert field in prompt
    assert "better_than" in prompt
    assert "higher" in prompt.lower() or "inverse" in prompt.lower()


def test_extract_code_strips_fences():
    from active_skill_system.application.use_cases.sandbox_agent_runner import _extract_code
    fenced = "```python\nx = 1\n```"
    assert _extract_code(fenced) == "x = 1"
    # No fence → best-effort raw.
    assert _extract_code("y = 2") == "y = 2"


def test_counter_increments_across_runs(tmp_path: Path):
    runner = SandboxAgentRunner(provider=_FakeProvider(), sandbox_dir=tmp_path)
    r1 = runner.run()
    r2 = runner.run()
    assert r1.loop.id != r2.loop.id
