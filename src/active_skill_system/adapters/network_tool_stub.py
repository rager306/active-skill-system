"""L3 Adapter — NetworkToolStub (M028 S02).

Deterministic stub simulating network routing transforms. Primary axis: latency_ms.

  REROUTE(target)       : latency_ms *= 0.7, hop_count -= 1
  COMPRESS(level)       : bandwidth_mbps *= 1.5, latency_ms += 2.0
  ADD_CACHE             : latency_ms *= 0.5, bandwidth_mbps += 50.0
  SWITCH_PROTOCOL       : latency_ms *= 0.8, packet_loss_pct *= 0.3
"""

from __future__ import annotations

import json
from typing import Any

from active_skill_system.application.ports.tool import (
    ToolCapability,
    ToolProfile,
    ToolResult,
)
from active_skill_system.domain.network_types import NetworkMetrics, NetworkNodeKind


def _metrics_from_dict(d: dict[str, Any]) -> NetworkMetrics:
    if not isinstance(d, dict):
        raise ValueError(f"baseline must be a dict (got {type(d).__name__})")
    try:
        return NetworkMetrics(
            latency_ms=float(d["latency_ms"]),
            bandwidth_mbps=float(d["bandwidth_mbps"]),
            packet_loss_pct=float(d["packet_loss_pct"]),
            hop_count=int(d["hop_count"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except KeyError as e:
        raise ValueError(f"baseline missing required key: {e.args[0]!r}") from None
    except (TypeError, ValueError) as e:
        raise ValueError(f"baseline has invalid values: {e}") from None


def _apply_transform(kind: NetworkNodeKind, params: dict[str, Any], baseline: NetworkMetrics) -> NetworkMetrics:
    latency = float(baseline.latency_ms)
    bandwidth = float(baseline.bandwidth_mbps)
    packet_loss = float(baseline.packet_loss_pct)
    hop_count = baseline.hop_count

    if kind is NetworkNodeKind.NET_TRANSFORM_REROUTE:
        latency = max(0.0, latency * 0.7)
        hop_count = max(0, hop_count - 1)
    elif kind is NetworkNodeKind.NET_TRANSFORM_COMPRESS:
        level = int(params.get("level", 1))
        if level < 1:
            raise ValueError(f"level must be >= 1 (got {level!r})")
        bandwidth = bandwidth * 1.5
        latency = latency + 2.0 * level
    elif kind is NetworkNodeKind.NET_TRANSFORM_ADD_CACHE:
        latency = max(0.0, latency * 0.5)
        bandwidth = bandwidth + 50.0
    elif kind is NetworkNodeKind.NET_TRANSFORM_SWITCH_PROTOCOL:
        latency = max(0.0, latency * 0.8)
        packet_loss = max(0.0, packet_loss * 0.3)
    else:
        raise ValueError(f"unsupported network transform kind: {kind!r}")

    return NetworkMetrics(latency_ms=latency, bandwidth_mbps=bandwidth, packet_loss_pct=packet_loss, hop_count=hop_count, is_valid=True)


class NetworkToolStub:
    """NetworkToolStub class."""
    name = "network_apply_transform"
    capabilities = frozenset({ToolCapability.COMPUTE})
    profile = ToolProfile.NORMAL

    def invoke(self, args: dict[str, Any]) -> ToolResult:
        if not isinstance(args, dict):
            return ToolResult(text="", evidence_id=None, success=False)
        kind_raw = args.get("transform_type")
        params_raw = args.get("params", {})
        baseline_raw = args.get("baseline")
        if kind_raw is None:
            try:
                baseline = _metrics_from_dict(baseline_raw if isinstance(baseline_raw, dict) else {})
            except ValueError:
                return ToolResult(text="", evidence_id=None, success=False)
            return ToolResult(
                text=json.dumps(_metrics_to_dict(baseline), sort_keys=True),
                evidence_id="missing_transform", success=True,
            )
        try:
            kind = NetworkNodeKind(kind_raw) if not isinstance(kind_raw, NetworkNodeKind) else kind_raw
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)
        try:
            baseline = _metrics_from_dict(baseline_raw if isinstance(baseline_raw, dict) else {})
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)
        if not isinstance(params_raw, dict):
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)
        if params_raw.get("legal", True) is False:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)
        try:
            new_metrics = _apply_transform(kind, params_raw, baseline)
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)
        return ToolResult(
            text=json.dumps(_metrics_to_dict(new_metrics), sort_keys=True),
            evidence_id=str(kind_raw), success=True,
        )


def _metrics_to_dict(m: NetworkMetrics) -> dict[str, Any]:
    return {"latency_ms": m.latency_ms, "bandwidth_mbps": m.bandwidth_mbps, "packet_loss_pct": m.packet_loss_pct, "hop_count": m.hop_count, "is_valid": m.is_valid}
