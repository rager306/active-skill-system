"""Tests for LogToolStub + LogRepairPolicy + LogEvolvable + composition (M030 S02+S03)."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from active_skill_system.adapters.log_tool_stub import LogToolStub
from active_skill_system.application.use_cases.log_repair_policy import LogRepairPolicy
from active_skill_system.composition import log_evolution
from active_skill_system.domain.evolvable import Evolvable
from active_skill_system.domain.log_types import (
    LogActionType,
    LogGapClass,
    LogMetrics,
    LogNodeKind,
    LogTransformParams,
)


def _baseline_dict(error_rate: float = 0.1, volume: float = 500.0, parse: float = 1000.0) -> dict:
    return {"error_rate": error_rate, "log_volume_mb": volume, "parse_time_ms": parse, "is_valid": True}


# ── LogToolStub ──────────────────────────────────────────────────────────


def test_filter_reduces_error_rate_and_volume() -> None:
    tool = LogToolStub()
    result = tool.invoke({"transform_type": "log_transform_filter", "params": {"level": "ERROR"}, "baseline": _baseline_dict(error_rate=0.1, volume=500.0)})
    assert result.success is True
    parsed = json.loads(result.text)
    assert abs(parsed["error_rate"] - 0.05) < 1e-9
    assert abs(parsed["log_volume_mb"] - 350.0) < 1e-9


def test_aggregate_halves_parse_time() -> None:
    tool = LogToolStub()
    result = tool.invoke({"transform_type": "log_transform_aggregate", "params": {}, "baseline": _baseline_dict(parse=1000.0)})
    parsed = json.loads(result.text)
    assert abs(parsed["parse_time_ms"] - 500.0) < 1e-9


def test_sample_reduces_volume() -> None:
    tool = LogToolStub()
    result = tool.invoke({"transform_type": "log_transform_sample", "params": {"rate": 0.1}, "baseline": _baseline_dict(volume=500.0, parse=1000.0)})
    parsed = json.loads(result.text)
    assert abs(parsed["log_volume_mb"] - 50.0) < 1e-9
    assert abs(parsed["parse_time_ms"] - 100.0) < 1e-9


def test_rotate_halves_volume_and_parse() -> None:
    tool = LogToolStub()
    result = tool.invoke({"transform_type": "log_transform_rotate", "params": {}, "baseline": _baseline_dict(volume=500.0, parse=1000.0)})
    parsed = json.loads(result.text)
    assert abs(parsed["log_volume_mb"] - 250.0) < 1e-9
    assert abs(parsed["parse_time_ms"] - 500.0) < 1e-9


def test_tool_missing_transform_returns_baseline() -> None:
    tool = LogToolStub()
    result = tool.invoke({"baseline": _baseline_dict()})
    assert result.success is True
    assert result.evidence_id == "missing_transform"


def test_tool_illegal_returns_failure() -> None:
    tool = LogToolStub()
    result = tool.invoke({"transform_type": "log_transform_filter", "params": {"legal": False}, "baseline": _baseline_dict()})
    assert result.success is False


# ── LogRepairPolicy ──────────────────────────────────────────────────────


def test_default_policy_maps_every_gap() -> None:
    policy = LogRepairPolicy.default_policy()
    for gap in LogGapClass:
        assert policy.covers(gap)


def test_default_policy_specific() -> None:
    policy = LogRepairPolicy.default_policy()
    assert policy.action_for(LogGapClass.HIGH_ERROR_RATE) is LogActionType.FILTER
    assert policy.action_for(LogGapClass.LOG_BLOAT) is LogActionType.SAMPLE


def test_action_for_falls_back_to_rotate() -> None:
    policy = LogRepairPolicy(mapping={LogGapClass.HIGH_ERROR_RATE: LogActionType.FILTER})
    assert policy.action_for(LogGapClass.RETENTION_VIOLATION) is LogActionType.ROTATE


# ── LogEvolvable ─────────────────────────────────────────────────────────


def test_build_log_evolvable_returns_evolvable() -> None:
    e = log_evolution._build_log_evolvable()
    assert isinstance(e, Evolvable)


def test_log_evolvable_evaluates_correctly() -> None:
    e = log_evolution._build_log_evolvable()
    cand = LogTransformParams(transform_type=LogNodeKind.LOG_TRANSFORM_FILTER, params={"level": "ERROR"}, legal=True)
    result = e.evaluate((cand,), {"baseline_metrics": _baseline_dict(error_rate=0.1, volume=500.0)})
    # FILTER: error_rate 0.1 -> 0.05 = 50% reduction; volume 500 -> 350 = 30% reduction.
    # Combined: 0.5*0.7 + 0.3*0.3 = 0.44.
    assert result.quality == pytest.approx(0.44)
    assert result.regression is False


def test_log_evolvable_mutate_decreases_sample_rate() -> None:
    from active_skill_system.application.evolvable_adapters import LogEvolvable
    e = LogEvolvable(invoker=lambda args: (True, json.dumps({"error_rate": 0.1, "log_volume_mb": 500.0, "parse_time_ms": 1000.0, "is_valid": True})))
    cand = LogTransformParams(transform_type=LogNodeKind.LOG_TRANSFORM_SAMPLE, params={"rate": 0.5}, legal=True)
    mutated = e.mutate((cand,))
    assert mutated[0].params["rate"] == pytest.approx(0.45)


# ── run_log_evolution ────────────────────────────────────────────────────


def test_run_log_evolution_promotes() -> None:
    """Single SAMPLE candidate: mutation bumps rate → better (lower volume) promotion."""
    result = log_evolution.run_log_evolution(
        LogMetrics(error_rate=0.1, log_volume_mb=500.0, parse_time_ms=1000.0, is_valid=True),
        (LogTransformParams(transform_type=LogNodeKind.LOG_TRANSFORM_SAMPLE, params={"rate": 0.1}, legal=True),),
        max_iterations=5,
    )
    assert result.promoted is True
    assert result.candidate_fitness.quality > result.baseline_fitness.quality


def test_default_candidates_have_three_transforms() -> None:
    candidates = log_evolution._default_candidates()
    assert len(candidates) == 3


# ── main() CLI ───────────────────────────────────────────────────────────


def test_main_default_args_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = log_evolution.main(["--baseline-error-rate", "0.1", "--max-iterations", "2"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PROMOTED" in captured.out or "No improvement" in captured.out


def test_main_rejects_out_of_range_error_rate(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = log_evolution.main(["--baseline-error-rate", "1.5", "--max-iterations", "1"])
    assert exit_code == 2


# ── R008 / R009 ──────────────────────────────────────────────────────────


def test_module_import_has_no_side_effects() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import active_skill_system.composition.log_evolution"],
        capture_output=True, text=True, timeout=10, cwd="/root/active-skill-system",
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_module_source_has_no_module_level_infra_imports() -> None:
    tree = ast.parse(Path(log_evolution.__file__).read_text(encoding="utf-8"))
    module_level_imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_level_imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module_level_imports.append(node.module or "")
    forbidden = ("activegraph", "anthropic", "openai", "log_tool_stub", "evolvable_adapters", "log_types")
    for imp in module_level_imports:
        for f in forbidden:
            assert f not in imp, f"module-level import {imp!r} references {f!r}"
