"""Tests for BwrapExecutor and InProcessExecutor (M044 S01)."""

from __future__ import annotations

from pathlib import Path

import pytest

from active_skill_system.adapters.bwrap_executor import BwrapExecutor
from active_skill_system.adapters.inprocess_executor import InProcessExecutor
from active_skill_system.application.ports.code_executor import CodeExecutorPort
from active_skill_system.domain.loop import LoopState

_FULL = "tests/fixtures/sandbox/cache_full.py"
_BROKEN = "tests/fixtures/sandbox/cache_broken.py"


# ── Protocol conformance ─────────────────────────────────────────────


def test_inprocess_is_code_executor():
    assert isinstance(InProcessExecutor(), CodeExecutorPort)


def test_bwrap_is_code_executor():
    assert isinstance(BwrapExecutor(), CodeExecutorPort)


# ── InProcessExecutor ────────────────────────────────────────────────


def test_inprocess_full_candidate_ok():
    r = InProcessExecutor().execute(_FULL)
    assert r.ok is True
    assert r.exit_code == 0


def test_inprocess_missing_file():
    r = InProcessExecutor().execute("nonexistent.py")
    assert r.ok is False
    assert r.error is not None


# ── BwrapExecutor ────────────────────────────────────────────────────


def test_bwrap_full_candidate_ok():
    r = BwrapExecutor().execute(_FULL)
    assert r.ok is True
    assert r.stdout == "OK"


def test_bwrap_missing_file():
    r = BwrapExecutor().execute("nonexistent.py")
    assert r.ok is False
    assert "not found" in (r.error or "")


def test_bwrap_broken_candidate_reports_error():
    """Broken candidate (wrong fields) loads but verifier catches it separately.
    The executor just checks loadability — import succeeds (syntactically valid)."""
    r = BwrapExecutor().execute(_BROKEN)
    # Broken fixture is syntactically valid Python — import succeeds.
    assert r.ok is True


# ── REAL-LLM test (gated --runllm) ───────────────────────────────────


@pytest.mark.llm
def test_real_llm_bwrap_executor_scores_full(tmp_path: Path):
    """REAL-LLM: generate cache_types via minimax/MiniMax-M3, execute in
    bubblewrap sandbox, verify scores 1.0. Gated behind --runllm.

    uv run pytest --runllm -k real_llm_bwrap -p no:cacheprovider
    """
    from active_skill_system.adapters.llm.minimax import MiniMaxProvider, load_env
    from active_skill_system.adapters.plain_llm_strategy import PlainLLMStrategy
    from active_skill_system.application.use_cases.sandbox_agent_runner import SandboxAgentRunner

    load_env()
    engine = PlainLLMStrategy(provider=MiniMaxProvider())
    runner = SandboxAgentRunner(
        engine=engine, sandbox_dir=tmp_path, code_executor=BwrapExecutor()
    )
    result = runner.run(model="minimax/MiniMax-M3")

    assert result.loop.state is LoopState.DONE, f"loop failed: {result.error}"
    assert result.fitness.score == 1.0, f"score {result.fitness.score} != 1.0"
    assert result.generated_path is not None
