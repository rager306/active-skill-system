"""End-to-end CLI smoke for composition/sql_evolution.py (M018 S03)."""

from __future__ import annotations

import subprocess
import sys


def _run_cli(*args: str, cwd: str = "/root/active-skill-system") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "active_skill_system.composition.sql_evolution", *args],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=cwd,
    )


def test_cli_default_args_promote_with_rows_examined_summary() -> None:
    """Default CLI must exit 0 and print PROMOTED + rows_examined reduction."""
    result = _run_cli("--baseline-rows", "1000", "--max-iterations", "3")
    assert result.returncode == 0
    assert "PROMOTED" in result.stdout
    assert "rows_examined reduction" in result.stdout
    assert "reason:" in result.stdout


def test_cli_at_cap_no_improvement() -> None:
    """baseline_rows=10 with default ADD_INDEX cols=5 already gives max reduction (10/5=2 rows)."""
    result = _run_cli("--baseline-rows", "10", "--max-iterations", "1")
    assert result.returncode == 0
    assert "No improvement" in result.stdout or "PROMOTED" in result.stdout


def test_cli_rejects_invalid_baseline_rows() -> None:
    result = _run_cli("--baseline-rows", "0", "--max-iterations", "1")
    assert result.returncode == 2
    combined = result.stdout + result.stderr
    assert "baseline-rows" in combined


def test_cli_rejects_invalid_max_iterations() -> None:
    result = _run_cli("--baseline-rows", "100", "--max-iterations", "0")
    assert result.returncode == 2
    combined = result.stdout + result.stderr
    assert "max-iterations" in combined


def test_cli_quiet_suppresses_preamble() -> None:
    result = _run_cli("--baseline-rows", "1000", "--max-iterations", "2", "--quiet")
    assert result.returncode == 0
    assert "---" not in result.stdout
    assert "baseline:" not in result.stdout
    assert "candidate_fitness" in result.stdout


def test_cli_loads_candidate_spec(tmp_path) -> None:
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(
        """[{"transform_type": "sql_transform_add_index", "params": {"cols": 8}, "legal": true}]""",
        encoding="utf-8",
    )
    result = _run_cli(
        "--baseline-rows", "1000", "--max-iterations", "2",
        "--candidate-spec", str(spec_file),
    )
    assert result.returncode == 0
    assert "candidates: 1" in result.stdout
    assert "kinds=['sql_transform_add_index']" in result.stdout
