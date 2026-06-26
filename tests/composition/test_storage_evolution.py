"""Tests for StorageToolStub + StorageRepairPolicy + StorageEvolvable + composition (M029 S02+S03)."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from active_skill_system.adapters.storage_tool_stub import StorageToolStub
from active_skill_system.application.use_cases.storage_repair_policy import StorageRepairPolicy
from active_skill_system.composition import storage_evolution
from active_skill_system.domain.evolvable import Evolvable
from active_skill_system.domain.storage_types import (
    StorageActionType,
    StorageGapClass,
    StorageMetrics,
    StorageNodeKind,
    StorageTransformParams,
)


def _baseline_dict(bytes_: int = 1000000, latency: float = 50.0) -> dict:
    return {"storage_bytes": bytes_, "query_latency_ms": latency, "index_count": 5, "is_valid": True}


# ── StorageToolStub ──────────────────────────────────────────────────────


def test_compress_reduces_bytes() -> None:
    tool = StorageToolStub()
    result = tool.invoke({"transform_type": "stor_transform_compress", "params": {"ratio": 0.5}, "baseline": _baseline_dict(bytes_=1000000)})
    assert result.success is True
    parsed = json.loads(result.text)
    assert parsed["storage_bytes"] == 500000


def test_partition_reduces_latency() -> None:
    tool = StorageToolStub()
    result = tool.invoke({"transform_type": "stor_transform_partition", "params": {"n_partitions": 4}, "baseline": _baseline_dict(latency=50.0)})
    parsed = json.loads(result.text)
    assert abs(parsed["query_latency_ms"] - 12.5) < 1e-9


def test_reindex_halves_latency() -> None:
    tool = StorageToolStub()
    result = tool.invoke({"transform_type": "stor_transform_reindex", "params": {}, "baseline": _baseline_dict(latency=50.0)})
    parsed = json.loads(result.text)
    assert abs(parsed["query_latency_ms"] - 25.0) < 1e-9
    assert parsed["index_count"] == 6


def test_tool_missing_transform_returns_baseline() -> None:
    tool = StorageToolStub()
    result = tool.invoke({"baseline": _baseline_dict()})
    assert result.success is True
    assert result.evidence_id == "missing_transform"


def test_tool_illegal_returns_failure() -> None:
    tool = StorageToolStub()
    result = tool.invoke({"transform_type": "stor_transform_compress", "params": {"ratio": 0.5, "legal": False}, "baseline": _baseline_dict()})
    assert result.success is False


# ── StorageRepairPolicy ──────────────────────────────────────────────────


def test_default_policy_maps_every_gap() -> None:
    policy = StorageRepairPolicy.default_policy()
    for gap in StorageGapClass:
        assert policy.covers(gap)


def test_default_policy_specific() -> None:
    policy = StorageRepairPolicy.default_policy()
    assert policy.action_for(StorageGapClass.BLOAT) is StorageActionType.COMPRESS
    assert policy.action_for(StorageGapClass.SLOW_QUERY) is StorageActionType.PARTITION


def test_action_for_falls_back_to_reindex() -> None:
    policy = StorageRepairPolicy(mapping={StorageGapClass.BLOAT: StorageActionType.COMPRESS})
    assert policy.action_for(StorageGapClass.SLOW_QUERY) is StorageActionType.REINDEX


# ── StorageEvolvable ─────────────────────────────────────────────────────


def test_build_storage_evolvable_returns_evolvable() -> None:
    e = storage_evolution._build_storage_evolvable()
    assert isinstance(e, Evolvable)


def test_storage_evolvable_evaluates_correctly() -> None:
    e = storage_evolution._build_storage_evolvable()
    cand = StorageTransformParams(transform_type=StorageNodeKind.STOR_TRANSFORM_COMPRESS, params={"ratio": 0.5}, legal=True)
    result = e.evaluate((cand,), {"baseline_metrics": _baseline_dict(bytes_=1000000)})
    # COMPRESS(0.5): 1000000 -> 500000 = 50% reduction.
    assert result.quality == pytest.approx(0.5)
    assert result.regression is False


def test_storage_evolvable_mutate_increases_ratio() -> None:
    from active_skill_system.application.evolvable_adapters import StorageEvolvable
    e = StorageEvolvable(invoker=lambda args: (True, json.dumps({"storage_bytes": 1000000, "query_latency_ms": 50.0, "index_count": 5, "is_valid": True})))
    cand = StorageTransformParams(transform_type=StorageNodeKind.STOR_TRANSFORM_COMPRESS, params={"ratio": 0.3}, legal=True)
    mutated = e.mutate((cand,))
    assert mutated[0].params["ratio"] == pytest.approx(0.4)


# ── run_storage_evolution ────────────────────────────────────────────────


def test_run_storage_evolution_promotes() -> None:
    result = storage_evolution.run_storage_evolution(
        StorageMetrics(storage_bytes=1000000, query_latency_ms=50.0, index_count=5, is_valid=True),
        (StorageTransformParams(transform_type=StorageNodeKind.STOR_TRANSFORM_COMPRESS, params={"ratio": 0.3}, legal=True),),
        max_iterations=5,
    )
    assert result.promoted is True


def test_default_candidates_have_three_transforms() -> None:
    candidates = storage_evolution._default_candidates()
    assert len(candidates) == 3


# ── main() CLI ───────────────────────────────────────────────────────────


def test_main_default_args_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = storage_evolution.main(["--baseline-bytes", "1000000", "--max-iterations", "2"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PROMOTED" in captured.out or "No improvement" in captured.out


def test_main_rejects_negative_bytes(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = storage_evolution.main(["--baseline-bytes", "-1", "--max-iterations", "1"])
    assert exit_code == 2


# ── R008 / R009 ──────────────────────────────────────────────────────────


def test_module_import_has_no_side_effects() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import active_skill_system.composition.storage_evolution"],
        capture_output=True, text=True, timeout=10, cwd="/root/active-skill-system",
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_module_source_has_no_module_level_infra_imports() -> None:
    tree = ast.parse(Path(storage_evolution.__file__).read_text(encoding="utf-8"))
    module_level_imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_level_imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module_level_imports.append(node.module or "")
    forbidden = ("activegraph", "anthropic", "openai", "storage_tool_stub", "evolvable_adapters", "storage_types")
    for imp in module_level_imports:
        for f in forbidden:
            assert f not in imp, f"module-level import {imp!r} references {f!r}"
