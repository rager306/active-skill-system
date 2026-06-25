"""Tests for composition/iac_evolution.py (M023 S03)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from active_skill_system.composition import iac_evolution
from active_skill_system.domain.evolvable import Evolvable
from active_skill_system.domain.iac_types import (
    IaCNodeKind,
    IaCPlanMetrics,
    IaCTransformParams,
)


def _baseline(resources: int = 100) -> IaCPlanMetrics:
    return IaCPlanMetrics(resource_count=resources, module_count=10, variable_count=20, drift_score=0.5, is_valid=True)


def _remove_unused() -> IaCTransformParams:
    return IaCTransformParams(transform_type=IaCNodeKind.IA_TRANSFORM_REMOVE_UNUSED, params={"variable_name": "x"}, legal=True)


def _add_output() -> IaCTransformParams:
    return IaCTransformParams(transform_type=IaCNodeKind.IA_TRANSFORM_ADD_OUTPUT, params={}, legal=True)


def _restructure_dep() -> IaCTransformParams:
    return IaCTransformParams(transform_type=IaCNodeKind.IA_TRANSFORM_RESTRUCTURE_DEP, params={}, legal=True)


# ── _build_iac_evolvable ─────────────────────────────────────────────────


def test_build_iac_evolvable_returns_evolvable() -> None:
    e = iac_evolution._build_iac_evolvable()
    assert isinstance(e, Evolvable)


def test_build_iac_evolvable_invokes_real_iac_tool_stub() -> None:
    e = iac_evolution._build_iac_evolvable()
    # Use a candidate that actually improves resource_count (REPLAN_PROVIDERS halves it).
    from active_skill_system.domain.iac_types import IaCNodeKind, IaCTransformParams
    replan = IaCTransformParams(
        transform_type=IaCNodeKind.IA_TRANSFORM_REPLAN_PROVIDERS, params={}, legal=True,
    )
    result = e.evaluate(
        (replan,),
        {"baseline_metrics": {"resource_count": 100, "module_count": 10, "variable_count": 20, "drift_score": 0.5, "is_valid": True}},
    )
    # REPLAN_PROVIDERS: resource_count 100 -> 50 = 50% reduction.
    assert result.quality == pytest.approx(0.5)
    assert result.regression is False


# ── run_iac_evolution ────────────────────────────────────────────────────


def test_run_iac_evolution_returns_promotion_result() -> None:
    baseline = _baseline(resources=100)
    candidates = (_remove_unused(), _add_output(), _restructure_dep())
    result = iac_evolution.run_iac_evolution(baseline, candidates, max_iterations=3)
    assert hasattr(result, "promoted")
    assert hasattr(result, "iterations_used")


def test_run_iac_evolution_accepts_injected_evolvable() -> None:
    class _FakeEvolvable:
        @property
        def mutation_space(self):
            from active_skill_system.domain.evolvable import MutationSpace
            return MutationSpace(description="fake", mutate_fn_name="fake")
        def mutate(self, genome):
            return genome
        def evaluate(self, genome, dataset):
            from active_skill_system.domain.evolvable import FitnessSignal
            return FitnessSignal(quality=0.5, cost=1.0, latency=1.0)
    result = iac_evolution.run_iac_evolution(_baseline(), (_remove_unused(),), max_iterations=2, evolvable=_FakeEvolvable())
    assert result.promoted is False


# ── _default_candidates ──────────────────────────────────────────────────


def test_default_candidates_have_three_iac_transforms() -> None:
    candidates = iac_evolution._default_candidates()
    assert len(candidates) == 3
    kinds = {c.transform_type for c in candidates}
    assert IaCNodeKind.IA_TRANSFORM_REMOVE_UNUSED in kinds
    assert IaCNodeKind.IA_TRANSFORM_ADD_OUTPUT in kinds
    assert IaCNodeKind.IA_TRANSFORM_RESTRUCTURE_DEP in kinds


# ── _load_candidate_spec ─────────────────────────────────────────────────


def test_load_candidate_spec_reads_json(tmp_path: Path) -> None:
    spec = [{"transform_type": "ia_transform_remove_unused", "params": {"variable_name": "y"}, "legal": True}]
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(__import__("json").dumps(spec), encoding="utf-8")
    candidates = iac_evolution._load_candidate_spec(str(spec_file))
    assert candidates[0].transform_type is IaCNodeKind.IA_TRANSFORM_REMOVE_UNUSED


def test_load_candidate_spec_rejects_non_list(tmp_path: Path) -> None:
    spec_file = tmp_path / "spec.json"
    spec_file.write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(ValueError, match="JSON list"):
        iac_evolution._load_candidate_spec(str(spec_file))


# ── main() CLI ───────────────────────────────────────────────────────────


def test_main_with_default_args_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = iac_evolution.main(["--baseline-resources", "100", "--max-iterations", "2"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PROMOTED" in captured.out or "No improvement" in captured.out


def test_main_rejects_invalid_baseline_resources(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = iac_evolution.main(["--baseline-resources", "0", "--max-iterations", "1"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "baseline-resources" in captured.out


def test_main_loads_candidate_spec(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import json
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(
        json.dumps([{"transform_type": "ia_transform_remove_unused", "params": {}, "legal": True}]),
        encoding="utf-8",
    )
    exit_code = iac_evolution.main(
        ["--baseline-resources", "100", "--max-iterations", "1", "--candidate-spec", str(spec_file)]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "candidates: 1" in captured.out


# ── R008 / R009 ────────────────────────────────────────────────────────


def test_module_import_has_no_side_effects() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import active_skill_system.composition.iac_evolution"],
        capture_output=True, text=True, timeout=10, cwd="/root/active-skill-system",
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_module_source_has_no_module_level_infra_imports() -> None:
    import ast
    tree = ast.parse(Path(iac_evolution.__file__).read_text(encoding="utf-8"))
    module_level_imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_level_imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module_level_imports.append(node.module or "")
    forbidden = ("activegraph", "anthropic", "openai", "iac_tool_stub", "iac_repair_policy", "evolvable_adapters", "iac_types")
    for imp in module_level_imports:
        for f in forbidden:
            assert f not in imp, f"module-level import {imp!r} references {f!r}"
