"""Tests for SQL evolution structured run logging (M039 S02 T02)."""

from __future__ import annotations

import json
from pathlib import Path

from active_skill_system.composition import sql_evolution


def _invoke_main_with_flag(tmp_path: Path, argv: list[str]) -> tuple[int, str]:
    """Run sql_evolution.main inside tmp_path; return (exit_code, captured_stdout)."""
    import contextlib
    import io

    out = io.StringIO()
    with contextlib.chdir(tmp_path), contextlib.redirect_stdout(out):
        exit_code = sql_evolution.main(argv)
    return exit_code, out.getvalue()


def test_emit_runlog_writes_jsonl_with_required_keys(tmp_path: Path) -> None:
    exit_code, out = _invoke_main_with_flag(
        tmp_path,
        ["--baseline-rows", "1000", "--max-iterations", "1", "--quiet", "--emit-runlog"],
    )
    assert exit_code == 0
    assert "runlog:" in out
    # Locate the written runlog.
    runlogs = sorted((tmp_path / "runs").glob("sql_evolution.*.jsonl"))
    assert runlogs, "no runlog file was written"
    record = json.loads(runlogs[0].read_text(encoding="utf-8"))
    for key in (
        "timestamp",
        "domain",
        "tool",
        "baseline_fitness",
        "candidate_fitness",
        "promoted",
        "iterations_used",
        "reason",
    ):
        assert key in record, f"runlog missing key {key!r}"
    assert record["domain"] == "sql"
    assert record["tool"] == "stub"
    assert "quality" in record["baseline_fitness"]
    assert "quality" in record["candidate_fitness"]


def test_emit_runlog_records_real_tool(tmp_path: Path) -> None:
    _invoke_main_with_flag(
        tmp_path,
        ["--baseline-rows", "1000", "--max-iterations", "1", "--real", "--quiet", "--emit-runlog"],
    )
    runlogs = sorted((tmp_path / "runs").glob("sql_evolution.*.jsonl"))
    assert runlogs
    record = json.loads(runlogs[0].read_text(encoding="utf-8"))
    assert record["tool"] == "real"


def test_no_runlog_without_flag(tmp_path: Path) -> None:
    _invoke_main_with_flag(
        tmp_path, ["--baseline-rows", "1000", "--max-iterations", "1", "--quiet"]
    )
    runs_dir = tmp_path / "runs"
    assert not runs_dir.exists() or not list(runs_dir.glob("*.jsonl")), (
        "runlog was written without --emit-runlog"
    )


def test_runlog_is_single_jsonl_line(tmp_path: Path) -> None:
    _invoke_main_with_flag(
        tmp_path,
        ["--baseline-rows", "1000", "--max-iterations", "1", "--quiet", "--emit-runlog"],
    )
    runlogs = sorted((tmp_path / "runs").glob("sql_evolution.*.jsonl"))
    content = runlogs[0].read_text(encoding="utf-8")
    lines = [ln for ln in content.splitlines() if ln.strip()]
    assert len(lines) == 1, "runlog must be a single JSONL line"
    json.loads(lines[0])  # parses
