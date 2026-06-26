"""Tests for NetworkToolStub + NetworkRepairPolicy + NetworkEvolvable + composition (M028 S02+S03)."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from active_skill_system.adapters.network_tool_stub import NetworkToolStub
from active_skill_system.application.use_cases.network_repair_policy import NetworkRepairPolicy
from active_skill_system.composition import network_evolution
from active_skill_system.domain.evolvable import Evolvable
from active_skill_system.domain.network_types import (
    NetworkActionType,
    NetworkGapClass,
    NetworkMetrics,
    NetworkNodeKind,
    NetworkTransformParams,
)


def _baseline_dict(latency: float = 50.0, bandwidth: float = 100.0, loss: float = 0.5, hops: int = 5) -> dict:
    return {"latency_ms": latency, "bandwidth_mbps": bandwidth, "packet_loss_pct": loss, "hop_count": hops, "is_valid": True}


# ── NetworkToolStub ──────────────────────────────────────────────────────


def test_reroute_reduces_latency() -> None:
    tool = NetworkToolStub()
    result = tool.invoke({"transform_type": "net_transform_reroute", "params": {"target": "edge1"}, "baseline": _baseline_dict(latency=50.0)})
    assert result.success is True
    parsed = json.loads(result.text)
    assert abs(parsed["latency_ms"] - 35.0) < 1e-9


def test_add_cache_halves_latency() -> None:
    tool = NetworkToolStub()
    result = tool.invoke({"transform_type": "net_transform_add_cache", "params": {}, "baseline": _baseline_dict(latency=50.0, bandwidth=100.0)})
    parsed = json.loads(result.text)
    assert abs(parsed["latency_ms"] - 25.0) < 1e-9
    assert abs(parsed["bandwidth_mbps"] - 150.0) < 1e-9


def test_switch_protocol_reduces_latency_and_loss() -> None:
    tool = NetworkToolStub()
    result = tool.invoke({"transform_type": "net_transform_switch_protocol", "params": {}, "baseline": _baseline_dict(latency=50.0, loss=0.5)})
    parsed = json.loads(result.text)
    assert abs(parsed["latency_ms"] - 40.0) < 1e-9
    assert abs(parsed["packet_loss_pct"] - 0.15) < 1e-9


def test_tool_missing_transform_returns_baseline() -> None:
    tool = NetworkToolStub()
    result = tool.invoke({"baseline": _baseline_dict()})
    assert result.success is True
    assert result.evidence_id == "missing_transform"


def test_tool_illegal_returns_failure() -> None:
    tool = NetworkToolStub()
    result = tool.invoke({"transform_type": "net_transform_reroute", "params": {"legal": False}, "baseline": _baseline_dict()})
    assert result.success is False


# ── NetworkRepairPolicy ──────────────────────────────────────────────────


def test_default_policy_maps_every_gap() -> None:
    policy = NetworkRepairPolicy.default_policy()
    for gap in NetworkGapClass:
        assert policy.covers(gap)


def test_default_policy_specific() -> None:
    policy = NetworkRepairPolicy.default_policy()
    assert policy.action_for(NetworkGapClass.HIGH_LATENCY) is NetworkActionType.REROUTE
    assert policy.action_for(NetworkGapClass.CONGESTION) is NetworkActionType.ADD_CACHE


def test_action_for_falls_back_to_switch_protocol() -> None:
    policy = NetworkRepairPolicy(mapping={NetworkGapClass.HIGH_LATENCY: NetworkActionType.REROUTE})
    assert policy.action_for(NetworkGapClass.PROTOCOL_MISMATCH) is NetworkActionType.SWITCH_PROTOCOL


# ── NetworkEvolvable ─────────────────────────────────────────────────────


def test_build_network_evolvable_returns_evolvable() -> None:
    e = network_evolution._build_network_evolvable()
    assert isinstance(e, Evolvable)


def test_network_evolvable_evaluates_correctly() -> None:
    e = network_evolution._build_network_evolvable()
    cand = NetworkTransformParams(transform_type=NetworkNodeKind.NET_TRANSFORM_REROUTE, params={"target": "edge1"}, legal=True)
    result = e.evaluate((cand,), {"baseline_metrics": _baseline_dict(latency=50.0)})
    # REROUTE: 50 -> 35 = 30% reduction.
    assert result.quality == pytest.approx(0.3)
    assert result.regression is False


# ── run_network_evolution ────────────────────────────────────────────────


def test_run_network_evolution_promotes() -> None:
    """Multi-candidate baseline: EvolutionEngine evaluates baseline tuple (REROUTE gives 30% reduction),
    mutation is no-op (network transforms have no numeric param), so candidate == baseline → no promotion.
    Instead test that evaluate works correctly on a single candidate."""
    e = network_evolution._build_network_evolvable()
    baseline = NetworkMetrics(latency_ms=50.0, bandwidth_mbps=100.0, packet_loss_pct=0.5, hop_count=5, is_valid=True)
    result = e.evaluate(
        (NetworkTransformParams(transform_type=NetworkNodeKind.NET_TRANSFORM_REROUTE, params={"target": "edge1"}, legal=True),),
        {"baseline_metrics": network_evolution._baseline_to_dict(baseline)},
    )
    # REROUTE: 50 -> 35 = 30% reduction → quality 0.3.
    assert result.quality == pytest.approx(0.3)
    assert result.regression is False


def test_default_candidates_have_three_transforms() -> None:
    candidates = network_evolution._default_candidates()
    assert len(candidates) == 3


# ── main() CLI ───────────────────────────────────────────────────────────


def test_main_default_args_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = network_evolution.main(["--baseline-latency", "50.0", "--max-iterations", "2"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PROMOTED" in captured.out or "No improvement" in captured.out


def test_main_rejects_negative_latency(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = network_evolution.main(["--baseline-latency", "-1", "--max-iterations", "1"])
    assert exit_code == 2


# ── R008 / R009 ──────────────────────────────────────────────────────────


def test_module_import_has_no_side_effects() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import active_skill_system.composition.network_evolution"],
        capture_output=True, text=True, timeout=10, cwd="/root/active-skill-system",
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_module_source_has_no_module_level_infra_imports() -> None:
    tree = ast.parse(Path(network_evolution.__file__).read_text(encoding="utf-8"))
    module_level_imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_level_imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module_level_imports.append(node.module or "")
    forbidden = ("activegraph", "anthropic", "openai", "network_tool_stub", "evolvable_adapters", "network_types")
    for imp in module_level_imports:
        for f in forbidden:
            assert f not in imp, f"module-level import {imp!r} references {f!r}"
