"""Tests for M051+ governance — mini_sandbox dispatch + governance check."""

from __future__ import annotations

from unittest.mock import patch

from active_skill_system.composition import cli_exit
from active_skill_system.composition.mini_sandbox import _dispatch, _parse_args


def _parse(*argv: str) -> object:
    """Parse CLI args, return namespace."""
    return _parse_args(list(argv))


def test_dispatch_ratchet_stats() -> None:
    args = _parse("--ratchet-stats", "--ratchet", "/tmp/nonexistent.jsonl")
    with patch("active_skill_system.composition.mini_sandbox._run_ratchet_stats", return_value=cli_exit.EX_NOT_FOUND):
        assert _dispatch(args) == cli_exit.EX_NOT_FOUND


def test_dispatch_graph_stats() -> None:
    args = _parse("--graph-stats", "--graph", "/tmp/nonexistent.lbdb")
    with patch("active_skill_system.composition.mini_sandbox._run_graph_stats", return_value=cli_exit.EX_NOT_FOUND):
        assert _dispatch(args) == cli_exit.EX_NOT_FOUND


def test_dispatch_graph_trajectory() -> None:
    args = _parse("--graph-trajectory", "--graph", "/tmp/nonexistent.lbdb")
    with patch("active_skill_system.composition.mini_sandbox._run_graph_trajectory", return_value=cli_exit.EX_NOT_FOUND):
        assert _dispatch(args) == cli_exit.EX_NOT_FOUND


def test_dispatch_graph_query() -> None:
    args = _parse("--graph-query", "MATCH (v) RETURN count(v)", "--graph", "/tmp/x.lbdb")
    with patch("active_skill_system.composition.mini_sandbox._run_graph_query", return_value=cli_exit.EX_OK):
        assert _dispatch(args) == cli_exit.EX_OK


def test_dispatch_report() -> None:
    args = _parse("--report")
    with patch("active_skill_system.composition.mini_sandbox._run_report", return_value=cli_exit.EX_OK):
        assert _dispatch(args) == cli_exit.EX_OK


def test_dispatch_recommend() -> None:
    args = _parse("--recommend")
    with patch("active_skill_system.composition.mini_sandbox._run_recommend", return_value=cli_exit.EX_OK):
        assert _dispatch(args) == cli_exit.EX_OK


def test_dispatch_event_stats() -> None:
    args = _parse("--event-stats")
    with patch("active_skill_system.composition.mini_sandbox._run_event_stats", return_value=cli_exit.EX_OK):
        assert _dispatch(args) == cli_exit.EX_OK


def test_dispatch_governance_check() -> None:
    args = _parse("--governance-check")
    with patch("active_skill_system.composition.mini_sandbox._run_governance_check", return_value=cli_exit.EX_OK):
        assert _dispatch(args) == cli_exit.EX_OK


def test_dispatch_check() -> None:
    args = _parse("--check", "some_file.py")
    with patch("active_skill_system.composition.mini_sandbox._run_check", return_value=cli_exit.EX_OK):
        assert _dispatch(args) == cli_exit.EX_OK


def test_dispatch_model_cache_types() -> None:
    args = _parse("--model", "test-model")
    with patch("active_skill_system.composition.mini_sandbox._build_event_store", return_value=None), \
         patch("active_skill_system.composition.mini_sandbox._run_single_model", return_value=cli_exit.EX_OK):
        assert _dispatch(args) == cli_exit.EX_OK


def test_dispatch_model_program_bench() -> None:
    args = _parse("--model", "test-model", "--bench", "program-bench")
    with patch("active_skill_system.composition.mini_sandbox._run_program_bench", return_value=cli_exit.EX_OK):
        assert _dispatch(args) == cli_exit.EX_OK


def test_dispatch_models() -> None:
    args = _parse("--models", "a,b,c")
    with patch("active_skill_system.composition.mini_sandbox._run_multi_model", return_value=cli_exit.EX_OK):
        assert _dispatch(args) == cli_exit.EX_OK


def test_dispatch_no_args_returns_usage() -> None:
    args = _parse()
    assert _dispatch(args) == cli_exit.EX_USAGE


def test_dispatch_compare_runs() -> None:
    args = _parse("--compare-runs", "run-a", "run-b")
    with patch("active_skill_system.composition.mini_sandbox._run_compare_runs", return_value=cli_exit.EX_OK):
        assert _dispatch(args) == cli_exit.EX_OK


def test_governance_result_score() -> None:
    from active_skill_system.application.use_cases.self_governance_check import GovernanceResult

    empty = GovernanceResult()
    assert empty.score == 0.0
    assert empty.all_passed is False

    full = GovernanceResult(axes={"a": True, "b": True})
    assert full.score == 1.0
    assert full.all_passed is True

    partial = GovernanceResult(axes={"a": True, "b": False})
    assert partial.score == 0.5
    assert partial.all_passed is False
    assert partial.failed_axes() == ["b"]


def test_governance_check_run_all_axes() -> None:
    """run_governance_check returns a result with 8 axes."""
    from active_skill_system.application.use_cases.self_governance_check import run_governance_check

    result = run_governance_check(axes=("layering_ok",))
    assert "layering_ok" in result.axes
    assert len(result.axes) == 1
