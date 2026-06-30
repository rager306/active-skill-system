"""Tests for M049 S04 — CLI exit codes and structured failure logging."""

from __future__ import annotations

from pathlib import Path

from active_skill_system.composition.cli_exit import (
    ALL_EXIT_CODES,
    EX_NOT_FOUND,
    EX_OK,
    EX_PARTIAL,
    EX_USAGE,
    name_for,
)


def test_exit_constants_have_expected_values() -> None:
    assert EX_OK == 0
    assert EX_PARTIAL == 1
    assert EX_NOT_FOUND == 2
    assert EX_USAGE == 3


def test_all_exit_codes_lists_four() -> None:
    assert set(ALL_EXIT_CODES) == {EX_OK, EX_PARTIAL, EX_NOT_FOUND, EX_USAGE}


def test_name_for_known_codes() -> None:
    assert name_for(0) == "EX_OK"
    assert name_for(1) == "EX_PARTIAL"
    assert name_for(2) == "EX_NOT_FOUND"
    assert name_for(3) == "EX_USAGE"


def test_name_for_unknown_code() -> None:
    assert name_for(99) == "EX_UNKNOWN"
    assert name_for(-1) == "EX_UNKNOWN"


def test_run_ratchet_stats_missing_file_returns_ex_not_found(tmp_path: Path) -> None:
    """End-to-end: --ratchet-stats on a missing file returns EX_NOT_FOUND (2)."""
    from active_skill_system.composition.sandbox.graphs import run_ratchet_stats as _run_ratchet_stats

    missing = tmp_path / "does_not_exist.jsonl"
    code = _run_ratchet_stats(str(missing))
    assert code == EX_NOT_FOUND


def test_run_graph_stats_missing_file_returns_ex_not_found(tmp_path: Path) -> None:
    from active_skill_system.composition.sandbox.graphs import run_graph_stats as _run_graph_stats

    missing = tmp_path / "missing.lbdb"
    code = _run_graph_stats(str(missing))
    assert code == EX_NOT_FOUND


def test_run_graph_query_missing_file_returns_ex_not_found(tmp_path: Path) -> None:
    from active_skill_system.composition.sandbox.graphs import run_graph_query as _run_graph_query

    missing = tmp_path / "missing.lbdb"
    code = _run_graph_query(str(missing), "MATCH (v) RETURN count(v)")
    assert code == EX_NOT_FOUND


def test_run_graph_trajectory_missing_file_returns_ex_not_found(tmp_path: Path) -> None:
    from active_skill_system.composition.sandbox.graphs import run_graph_trajectory as _run_graph_trajectory

    missing = tmp_path / "missing.lbdb"
    code = _run_graph_trajectory(str(missing))
    assert code == EX_NOT_FOUND


def test_run_compare_runs_missing_returns_ex_not_found(tmp_path: Path) -> None:
    """End-to-end: --compare-runs on a missing run id returns EX_NOT_FOUND."""
    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore
    from active_skill_system.composition.sandbox.queries import run_compare_runs as _run_compare_runs

    # Build a real graph with one loop, then ask for a missing run id.
    graph_path = tmp_path / "graph.lbdb"
    LadybugGraphStore(str(graph_path)).close()
    # No data; the missing-id check happens before graph lookup.
    code = _run_compare_runs(str(graph_path), "sandbox-run-aaa", "sandbox-run-ghost", False, None)
    assert code == EX_NOT_FOUND
