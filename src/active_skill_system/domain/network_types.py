"""L1 Domain — Network routing optimization types (M028 S01).

Domain profile for network routing optimization. Mirrors compiler/SQL/IaC/security/ML
types shape. Primary fitness axis: latency_ms (lower = better). Triple-axis
ranking: latency_ms primary, bandwidth_mbps inverse (higher = better),
packet_loss_pct tie-breaker.

Pure domain. NO I/O, NO infrastructure imports (R002). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class NetworkNodeKind(StrEnum):
    """NetworkNodeKind class."""
    ROUTE = "route"
    GATEWAY = "gateway"
    LOAD_BALANCER = "load_balancer"
    FIREWALL = "firewall"
    NET_TRANSFORM_REROUTE = "net_transform_reroute"
    NET_TRANSFORM_COMPRESS = "net_transform_compress"
    NET_TRANSFORM_ADD_CACHE = "net_transform_add_cache"
    NET_TRANSFORM_SWITCH_PROTOCOL = "net_transform_switch_protocol"


class NetworkGapClass(StrEnum):
    """NetworkGapClass class."""
    HIGH_LATENCY = "high_latency"
    LOW_BANDWIDTH = "low_bandwidth"
    PACKET_LOSS = "packet_loss"
    CONGESTION = "congestion"
    PROTOCOL_MISMATCH = "protocol_mismatch"


class NetworkActionType(StrEnum):
    """NetworkActionType class."""
    REROUTE = "reroute"
    COMPRESS = "compress"
    ADD_CACHE = "add_cache"
    SWITCH_PROTOCOL = "switch_protocol"


@dataclass(frozen=True)
class NetworkTransformParams:
    """NetworkTransformParams class."""
    transform_type: NetworkNodeKind
    params: dict[str, Any]
    legal: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.transform_type, NetworkNodeKind):
            errors.append(f"transform_type must be a NetworkNodeKind (got {type(self.transform_type).__name__})")
        transform_kinds = {
            NetworkNodeKind.NET_TRANSFORM_REROUTE,
            NetworkNodeKind.NET_TRANSFORM_COMPRESS,
            NetworkNodeKind.NET_TRANSFORM_ADD_CACHE,
            NetworkNodeKind.NET_TRANSFORM_SWITCH_PROTOCOL,
        }
        if self.transform_type not in transform_kinds:
            errors.append(f"transform_type must be a NET_TRANSFORM_* kind (got {self.transform_type!r})")
        if not isinstance(self.params, dict):
            errors.append(f"params must be a dict (got {type(self.params).__name__})")
        if not isinstance(self.legal, bool):
            errors.append(f"legal must be a bool (got {type(self.legal).__name__})")
        if errors:
            raise ValueError("NetworkTransformParams invariant violation: " + "; ".join(errors))


@dataclass(frozen=True)
class NetworkMetrics:
    """Measured network routing metrics.

    Carries:
      - latency_ms: round-trip latency (float, >= 0.0; lower = better).
      - bandwidth_mbps: available bandwidth (float, >= 0.0; higher = better — inverse axis).
      - packet_loss_pct: packet loss percentage (float in [0, 100]; lower = better).
      - hop_count: number of network hops (int, >= 0; reported but not in ranking).
      - is_valid: False if the route is invalid.
    """

    latency_ms: float
    bandwidth_mbps: float
    packet_loss_pct: float
    hop_count: int
    is_valid: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.latency_ms, (int, float)) or isinstance(self.latency_ms, bool) or float(self.latency_ms) < 0.0:
            errors.append(f"latency_ms must be a non-negative number (got {self.latency_ms!r})")
        if not isinstance(self.bandwidth_mbps, (int, float)) or isinstance(self.bandwidth_mbps, bool) or float(self.bandwidth_mbps) < 0.0:
            errors.append(f"bandwidth_mbps must be a non-negative number (got {self.bandwidth_mbps!r})")
        if not isinstance(self.packet_loss_pct, (int, float)) or isinstance(self.packet_loss_pct, bool) or not (0.0 <= float(self.packet_loss_pct) <= 100.0):
            errors.append(f"packet_loss_pct must be in [0.0, 100.0] (got {self.packet_loss_pct!r})")
        if not isinstance(self.hop_count, int) or isinstance(self.hop_count, bool) or self.hop_count < 0:
            errors.append(f"hop_count must be a non-negative int (got {self.hop_count!r})")
        if not isinstance(self.is_valid, bool):
            errors.append(f"is_valid must be a bool (got {type(self.is_valid).__name__})")
        if errors:
            raise ValueError("NetworkMetrics invariant violation: " + "; ".join(errors))

    def better_than(self, other: NetworkMetrics) -> bool:
        """True if this metrics is strictly better than other.

        Invalid never beats valid. Among valid: strictly lower latency_ms wins,
        OR same latency with strictly higher bandwidth_mbps (inverse axis),
        OR same latency+bandwidth with strictly lower packet_loss_pct.
        hop_count is reported but not in the ranking.
        """
        if not isinstance(other, NetworkMetrics):
            return False
        if not self.is_valid and other.is_valid:
            return False
        if self.is_valid and not other.is_valid:
            return True
        if float(self.latency_ms) < float(other.latency_ms):
            return True
        if float(self.latency_ms) == float(other.latency_ms):
            if float(self.bandwidth_mbps) > float(other.bandwidth_mbps):
                return True
            if (
                float(self.bandwidth_mbps) == float(other.bandwidth_mbps)
                and float(self.packet_loss_pct) < float(other.packet_loss_pct)
            ):
                return True
        return False
