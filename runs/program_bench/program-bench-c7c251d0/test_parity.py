"""ProgramBench smallest-CLI parity tests (M053 S01, D014).

Tests that exercise the json_pretty CLI: parse various JSON inputs,
verify indented output, sort_keys behaviour, file vs stdin, error
handling. An LLM-generated candidate must pass these tests to satisfy
the parity check (ProgramBench model: behavioural parity, not source
parity).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_FIXTURE_DIR = Path('runs/program_bench/program-bench-c7c251d0/json_pretty.py').parent
_CLI = _FIXTURE_DIR / "json_pretty.py"


def _run_cli(*cli_args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_CLI), *cli_args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_cli_exists() -> None:
    assert _CLI.exists(), f"CLI fixture missing: {_CLI}"


def test_cli_empty_dict() -> None:
    r = _run_cli(stdin="{}")
    assert r.returncode == 0
    assert r.stdout.strip() == "{}"


def test_cli_simple_object_indented() -> None:
    r = _run_cli("--indent", "2", stdin='{"b": 2, "a": 1}')
    assert r.returncode == 0
    # Object keys are NOT sorted by default; insertion order preserved.
    assert '"b": 2' in r.stdout
    assert '"a": 1' in r.stdout


def test_cli_sort_keys_alphabetical() -> None:
    r = _run_cli("--sort-keys", stdin='{"b": 2, "a": 1}')
    assert r.returncode == 0
    a_pos = r.stdout.index('"a"')
    b_pos = r.stdout.index('"b"')
    assert a_pos < b_pos, f"'a' should appear before 'b' with --sort-keys, got: {r.stdout!r}"


def test_cli_nested_object() -> None:
    inp = '{"outer": {"inner": [1, 2, 3]}}'
    r = _run_cli("--indent", "2", stdin=inp)
    assert r.returncode == 0
    out = r.stdout
    parsed = json.loads(out)
    assert parsed == {"outer": {"inner": [1, 2, 3]}}


def test_cli_compact_mode_zero_indent() -> None:
    inp = '{"z": 1, "a": 2}'
    r = _run_cli("--indent", "0", "--sort-keys", stdin=inp)
    assert r.returncode == 0
    assert r.stdout.strip() == '{"a":2,"z":1}'


def test_cli_reads_from_file(tmp_path: Path) -> None:
    f = tmp_path / "data.json"
    f.write_text('{"file": true}', encoding="utf-8")
    r = _run_cli(str(f), "--indent", "2")
    assert r.returncode == 0
    parsed = json.loads(r.stdout)
    assert parsed == {"file": True}


def test_cli_invalid_json_exits_1() -> None:
    r = _run_cli(stdin="{not json")
    assert r.returncode == 1
    assert "invalid JSON" in r.stderr


def test_cli_array_with_sort_keys() -> None:
    """Arrays are NOT sorted by --sort-keys (only object keys)."""
    inp = '[{"z": 1}, {"a": 2}]'
    r = _run_cli("--sort-keys", stdin=inp)
    assert r.returncode == 0
    parsed = json.loads(r.stdout)
    assert parsed == [{"z": 1}, {"a": 2}]
