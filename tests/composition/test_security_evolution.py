"""Tests for SecurityEvolvable + composition/security_evolution.py (M026 S03)."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from active_skill_system.composition import security_evolution
from active_skill_system.domain.evolvable import Evolvable, FitnessSignal
from active_skill_system.domain.security_types import (
    SecurityMetrics,
    SecurityNodeKind,
    SecurityTransformParams,
)


def _baseline(threats: int = 50) -> SecurityMetrics:
    return SecurityMetrics(threat_count=threats, risk_score=7.5, coverage_ratio=0.6, exposure_time=100.0, is_valid=True)


def _patch(cve_count: int = 5) -> SecurityTransformParams:
    return SecurityTransformParams(transform_type=SecurityNodeKind.SEC_TRANSFORM_PATCH, params={"cve_count": cve_count}, legal=True)


def _add_control(controls: int = 2) -> SecurityTransformParams:
    return SecurityTransformParams(transform_type=SecurityNodeKind.SEC_TRANSFORM_ADD_CONTROL, params={"controls": controls}, legal=True)


def _isolate() -> SecurityTransformParams:
    return SecurityTransformParams(transform_type=SecurityNodeKind.SEC_TRANSFORM_ISOLATE, params={}, legal=True)


# ── _build_security_evolvable ────────────────────────────────────────────


def test_build_security_evolvable_returns_evolvable() -> None:
    e = security_evolution._build_security_evolvable()
    assert isinstance(e, Evolvable)


def test_build_security_evolvable_invokes_real_tool() -> None:
    e = security_evolution._build_security_evolvable()
    result = e.evaluate(
        (_patch(cve_count=5),),
        {"baseline_metrics": {"threat_count": 50, "risk_score": 7.5, "coverage_ratio": 0.6, "exposure_time": 100.0, "is_valid": True}},
    )
    # PATCH 5: threats 50 -> 45 = 10% reduction.
    assert result.quality == pytest.approx(0.1)
    assert result.regression is False


# ── run_security_evolution ───────────────────────────────────────────────


def test_run_security_evolution_promotes() -> None:
    """Single PATCH candidate: baseline PATCH(5) quality=0.1, mutated PATCH(6) quality=0.12 → promoted."""
    result = security_evolution.run_security_evolution(
        _baseline(threats=50), (_patch(cve_count=5),), max_iterations=5,
    )
    assert result.promoted is True
    assert result.candidate_fitness.quality > result.baseline_fitness.quality


def test_run_security_evolution_accepts_injected_evolvable() -> None:
    class _FakeEvolvable:
        @property
        def mutation_space(self):
            from active_skill_system.domain.evolvable import MutationSpace
            return MutationSpace(description="fake", mutate_fn_name="fake")
        def mutate(self, genome):
            return genome
        def evaluate(self, genome, dataset):
            return FitnessSignal(quality=0.5, cost=1.0, latency=1.0)
    result = security_evolution.run_security_evolution(
        _baseline(), (_patch(),), max_iterations=2, evolvable=_FakeEvolvable(),
    )
    assert result.promoted is False


# ── _default_candidates ──────────────────────────────────────────────────


def test_default_candidates_have_three_transforms() -> None:
    candidates = security_evolution._default_candidates()
    assert len(candidates) == 3


# ── main() CLI ───────────────────────────────────────────────────────────


def test_main_with_default_args_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = security_evolution.main(["--baseline-threats", "50", "--max-iterations", "2"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PROMOTED" in captured.out or "No improvement" in captured.out


def test_main_rejects_invalid_baseline_threats(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = security_evolution.main(["--baseline-threats", "0", "--max-iterations", "1"])
    assert exit_code == 2


# ── SecurityEvolvable mutation ───────────────────────────────────────────


def test_security_evolvable_mutate_bumps_patch_cve_count() -> None:
    from active_skill_system.application.evolvable_adapters import SecurityEvolvable
    e = SecurityEvolvable(invoker=lambda args: (True, json.dumps({"threat_count": 50, "risk_score": 7.5, "coverage_ratio": 0.6, "exposure_time": 100.0, "is_valid": True})))
    mutated = e.mutate((_patch(cve_count=5),))
    assert mutated[0].params["cve_count"] == 6


def test_security_evolvable_mutate_bumps_add_control() -> None:
    from active_skill_system.application.evolvable_adapters import SecurityEvolvable
    e = SecurityEvolvable(invoker=lambda args: (True, json.dumps({"threat_count": 50, "risk_score": 7.5, "coverage_ratio": 0.6, "exposure_time": 100.0, "is_valid": True})))
    mutated = e.mutate((_add_control(controls=2),))
    assert mutated[0].params["controls"] == 3


# ── R008 / R009 ────────────────────────────────────────────────────────


def test_module_import_has_no_side_effects() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import active_skill_system.composition.security_evolution"],
        capture_output=True, text=True, timeout=10, cwd="/root/active-skill-system",
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_module_source_has_no_module_level_infra_imports() -> None:
    tree = ast.parse(Path(security_evolution.__file__).read_text(encoding="utf-8"))
    module_level_imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_level_imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module_level_imports.append(node.module or "")
    forbidden = ("activegraph", "anthropic", "openai", "security_tool_stub", "evolvable_adapters", "security_types")
    for imp in module_level_imports:
        for f in forbidden:
            assert f not in imp, f"module-level import {imp!r} references {f!r}"
