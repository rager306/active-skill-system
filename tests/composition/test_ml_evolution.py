"""Tests for MLToolStub + MLRepairPolicy + MLEvolvable + composition (M027 S02+S03)."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from active_skill_system.adapters.ml_tool_stub import MLToolStub
from active_skill_system.application.use_cases.ml_repair_policy import MLRepairPolicy
from active_skill_system.composition import ml_evolution
from active_skill_system.domain.evolvable import Evolvable
from active_skill_system.domain.ml_types import (
    MLActionType,
    MLGapClass,
    MLMetrics,
    MLNodeKind,
    MLTransformParams,
)


def _baseline_dict(loss: float = 0.5, accuracy: float = 0.85, epochs: int = 100) -> dict:
    return {"loss": loss, "accuracy": accuracy, "epochs": epochs, "convergence_time": 3600.0, "is_valid": True}


# ── MLToolStub ───────────────────────────────────────────────────────────


def test_adjust_lr_reduces_loss() -> None:
    tool = MLToolStub()
    result = tool.invoke({"transform_type": "ml_transform_adjust_lr", "params": {"lr_factor": 0.5}, "baseline": _baseline_dict(loss=0.5)})
    assert result.success is True
    parsed = json.loads(result.text)
    assert abs(parsed["loss"] - 0.25) < 1e-9
    assert parsed["epochs"] == 95


def test_add_regularization_reduces_loss_and_increases_accuracy() -> None:
    tool = MLToolStub()
    result = tool.invoke({"transform_type": "ml_transform_add_regularization", "params": {}, "baseline": _baseline_dict(loss=0.5, accuracy=0.85)})
    parsed = json.loads(result.text)
    assert abs(parsed["loss"] - 0.475) < 1e-9
    assert abs(parsed["accuracy"] - 0.9) < 1e-9


def test_switch_optimizer_reduces_loss_and_epochs() -> None:
    tool = MLToolStub()
    result = tool.invoke({"transform_type": "ml_transform_switch_optimizer", "params": {}, "baseline": _baseline_dict(loss=0.5, epochs=100)})
    parsed = json.loads(result.text)
    assert abs(parsed["loss"] - 0.4) < 1e-9
    assert parsed["epochs"] == 80


def test_tool_missing_transform_returns_baseline() -> None:
    tool = MLToolStub()
    result = tool.invoke({"baseline": _baseline_dict()})
    assert result.success is True
    assert result.evidence_id == "missing_transform"


def test_tool_illegal_returns_failure() -> None:
    tool = MLToolStub()
    result = tool.invoke({"transform_type": "ml_transform_adjust_lr", "params": {"lr_factor": 0.5, "legal": False}, "baseline": _baseline_dict()})
    assert result.success is False


# ── MLRepairPolicy ───────────────────────────────────────────────────────


def test_default_policy_maps_every_gap() -> None:
    policy = MLRepairPolicy.default_policy()
    for gap in MLGapClass:
        assert policy.covers(gap)


def test_default_policy_specific() -> None:
    policy = MLRepairPolicy.default_policy()
    assert policy.action_for(MLGapClass.HIGH_LOSS) is MLActionType.ADJUST_LR
    assert policy.action_for(MLGapClass.OVERFITTING) is MLActionType.ADD_REGULARIZATION


def test_action_for_falls_back_to_switch_optimizer() -> None:
    policy = MLRepairPolicy(mapping={MLGapClass.HIGH_LOSS: MLActionType.ADJUST_LR})
    assert policy.action_for(MLGapClass.TRAINING_INSTABILITY) is MLActionType.SWITCH_OPTIMIZER


# ── MLEvolvable ──────────────────────────────────────────────────────────


def test_build_ml_evolvable_returns_evolvable() -> None:
    e = ml_evolution._build_ml_evolvable()
    assert isinstance(e, Evolvable)


def test_ml_evolvable_evaluates_correctly() -> None:
    e = ml_evolution._build_ml_evolvable()
    from active_skill_system.domain.ml_types import MLNodeKind, MLTransformParams
    cand = MLTransformParams(transform_type=MLNodeKind.ML_TRANSFORM_ADJUST_LR, params={"lr_factor": 0.5}, legal=True)
    result = e.evaluate((cand,), {"baseline_metrics": _baseline_dict(loss=0.5)})
    # ADJUST_LR(0.5): loss 0.5 -> 0.25 = 50% reduction.
    assert result.quality == pytest.approx(0.5)
    assert result.regression is False


def test_ml_evolvable_mutate_halves_lr_factor() -> None:
    from active_skill_system.application.evolvable_adapters import MLEvolvable
    e = MLEvolvable(invoker=lambda args: (True, json.dumps({"loss": 0.5, "accuracy": 0.85, "epochs": 100, "convergence_time": 3600.0, "is_valid": True})))
    cand = MLTransformParams(transform_type=MLNodeKind.ML_TRANSFORM_ADJUST_LR, params={"lr_factor": 0.5}, legal=True)
    mutated = e.mutate((cand,))
    assert mutated[0].params["lr_factor"] == 0.25


# ── run_ml_evolution ─────────────────────────────────────────────────────


def test_run_ml_evolution_promotes() -> None:
    result = ml_evolution.run_ml_evolution(
        MLMetrics(loss=0.5, accuracy=0.85, epochs=100, convergence_time=3600.0, is_valid=True),
        (MLTransformParams(transform_type=MLNodeKind.ML_TRANSFORM_ADJUST_LR, params={"lr_factor": 0.5}, legal=True),),
        max_iterations=5,
    )
    assert result.promoted is True


def test_default_candidates_have_three_transforms() -> None:
    candidates = ml_evolution._default_candidates()
    assert len(candidates) == 3


# ── main() CLI ───────────────────────────────────────────────────────────


def test_main_default_args_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = ml_evolution.main(["--baseline-loss", "0.5", "--max-iterations", "2"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PROMOTED" in captured.out or "No improvement" in captured.out


def test_main_rejects_negative_loss(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = ml_evolution.main(["--baseline-loss", "-1", "--max-iterations", "1"])
    assert exit_code == 2


# ── R008 / R009 ──────────────────────────────────────────────────────────


def test_module_import_has_no_side_effects() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import active_skill_system.composition.ml_evolution"],
        capture_output=True, text=True, timeout=10, cwd="/root/active-skill-system",
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_module_source_has_no_module_level_infra_imports() -> None:
    tree = ast.parse(Path(ml_evolution.__file__).read_text(encoding="utf-8"))
    module_level_imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_level_imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module_level_imports.append(node.module or "")
    forbidden = ("activegraph", "anthropic", "openai", "ml_tool_stub", "evolvable_adapters", "ml_types")
    for imp in module_level_imports:
        for f in forbidden:
            assert f not in imp, f"module-level import {imp!r} references {f!r}"
