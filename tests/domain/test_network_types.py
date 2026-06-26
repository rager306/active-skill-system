"""Tests for domain/network_types.py (M028 S01)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from active_skill_system.domain.network_types import (
    NetworkActionType,
    NetworkGapClass,
    NetworkMetrics,
    NetworkNodeKind,
    NetworkTransformParams,
)


def test_network_node_kind_has_plan_kinds() -> None:
    assert NetworkNodeKind.ROUTE.value == "route"
    assert NetworkNodeKind.GATEWAY.value == "gateway"
    assert NetworkNodeKind.LOAD_BALANCER.value == "load_balancer"
    assert NetworkNodeKind.FIREWALL.value == "firewall"


def test_network_node_kind_has_transform_kinds() -> None:
    assert NetworkNodeKind.NET_TRANSFORM_REROUTE.value == "net_transform_reroute"
    assert NetworkNodeKind.NET_TRANSFORM_COMPRESS.value == "net_transform_compress"
    assert NetworkNodeKind.NET_TRANSFORM_ADD_CACHE.value == "net_transform_add_cache"
    assert NetworkNodeKind.NET_TRANSFORM_SWITCH_PROTOCOL.value == "net_transform_switch_protocol"


def test_network_gap_class_has_five_values() -> None:
    assert len(NetworkGapClass) == 5
    assert NetworkGapClass.HIGH_LATENCY.value == "high_latency"
    assert NetworkGapClass.CONGESTION.value == "congestion"


def test_network_action_type_has_four_values() -> None:
    assert len(NetworkActionType) == 4
    assert NetworkActionType.REROUTE.value == "reroute"
    assert NetworkActionType.SWITCH_PROTOCOL.value == "switch_protocol"


def test_network_transform_params_accepts_valid_kind() -> None:
    p = NetworkTransformParams(transform_type=NetworkNodeKind.NET_TRANSFORM_REROUTE, params={"target": "edge1"}, legal=True)
    assert p.transform_type is NetworkNodeKind.NET_TRANSFORM_REROUTE


def test_network_transform_params_rejects_non_transform_kind() -> None:
    with pytest.raises(ValueError, match="NET_TRANSFORM"):
        NetworkTransformParams(transform_type=NetworkNodeKind.ROUTE, params={}, legal=True)


def test_network_transform_params_rejects_non_dict_params() -> None:
    with pytest.raises(ValueError, match="params must be a dict"):
        NetworkTransformParams(transform_type=NetworkNodeKind.NET_TRANSFORM_REROUTE, params=[1], legal=True)  # type: ignore[arg-type]


def _baseline_metrics(latency: float = 50.0) -> NetworkMetrics:
    return NetworkMetrics(latency_ms=latency, bandwidth_mbps=100.0, packet_loss_pct=0.5, hop_count=5, is_valid=True)


def test_network_metrics_rejects_negative_latency() -> None:
    with pytest.raises(ValueError, match="latency_ms"):
        NetworkMetrics(latency_ms=-1.0, bandwidth_mbps=100.0, packet_loss_pct=0.0, hop_count=1)


def test_network_metrics_rejects_packet_loss_out_of_range() -> None:
    with pytest.raises(ValueError, match="packet_loss_pct"):
        NetworkMetrics(latency_ms=50.0, bandwidth_mbps=100.0, packet_loss_pct=150.0, hop_count=1)


def test_network_metrics_better_than_strictly_lower_latency() -> None:
    base = _baseline_metrics(latency=50.0)
    better = _baseline_metrics(latency=30.0)
    assert better.better_than(base)
    assert not base.better_than(better)


def test_network_metrics_better_than_tie_break_by_bandwidth_higher() -> None:
    """bandwidth is inverse axis — higher is better (same latency)."""
    base = NetworkMetrics(latency_ms=50.0, bandwidth_mbps=100.0, packet_loss_pct=0.5, hop_count=5, is_valid=True)
    better = NetworkMetrics(latency_ms=50.0, bandwidth_mbps=200.0, packet_loss_pct=0.5, hop_count=5, is_valid=True)
    assert better.better_than(base)


def test_network_metrics_better_than_tie_break_by_packet_loss_lower() -> None:
    base = NetworkMetrics(latency_ms=50.0, bandwidth_mbps=100.0, packet_loss_pct=0.5, hop_count=5, is_valid=True)
    better = NetworkMetrics(latency_ms=50.0, bandwidth_mbps=100.0, packet_loss_pct=0.1, hop_count=5, is_valid=True)
    assert better.better_than(base)


def test_network_metrics_invalid_never_beats_valid() -> None:
    valid = _baseline_metrics(latency=999.0)
    invalid = NetworkMetrics(latency_ms=0.1, bandwidth_mbps=9999.0, packet_loss_pct=0.0, hop_count=1, is_valid=False)
    assert not invalid.better_than(valid)
    assert valid.better_than(invalid)


def test_network_metrics_hop_count_does_not_affect_ranking() -> None:
    base = NetworkMetrics(latency_ms=50.0, bandwidth_mbps=100.0, packet_loss_pct=0.5, hop_count=5, is_valid=True)
    same_other = NetworkMetrics(latency_ms=50.0, bandwidth_mbps=100.0, packet_loss_pct=0.5, hop_count=99, is_valid=True)
    assert not same_other.better_than(base)
    assert not base.better_than(same_other)


def test_network_metrics_better_than_handles_invalid_input() -> None:
    m = _baseline_metrics()
    assert not m.better_than("not metrics")  # type: ignore[arg-type]


def test_network_types_module_infra_free() -> None:
    mod = importlib.import_module("active_skill_system.domain.network_types")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"network_types.py must not contain '{forbidden}' (R002)"
