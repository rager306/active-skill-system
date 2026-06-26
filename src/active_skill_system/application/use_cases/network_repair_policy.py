"""L2 Application — NetworkRepairPolicy (M028 S02)."""

from __future__ import annotations

from dataclasses import dataclass, field

from active_skill_system.domain.network_types import NetworkActionType, NetworkGapClass


@dataclass(frozen=True)
class NetworkRepairPolicy:
    mapping: dict[NetworkGapClass, NetworkActionType] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.mapping, dict):
            errors.append("mapping must be a dict")
        elif not self.mapping:
            errors.append("mapping must be non-empty")
        else:
            for gap, action in self.mapping.items():
                if not isinstance(gap, NetworkGapClass):
                    errors.append("keys must be NetworkGapClass")
                if not isinstance(action, NetworkActionType):
                    errors.append("values must be NetworkActionType")
        if errors:
            raise ValueError("NetworkRepairPolicy invariant violation: " + "; ".join(errors))

    def action_for(self, gap: NetworkGapClass) -> NetworkActionType:
        return self.mapping.get(gap, NetworkActionType.SWITCH_PROTOCOL)

    def covers(self, gap: NetworkGapClass) -> bool:
        return gap in self.mapping

    @staticmethod
    def default_policy() -> NetworkRepairPolicy:
        return NetworkRepairPolicy(mapping={
            NetworkGapClass.HIGH_LATENCY: NetworkActionType.REROUTE,
            NetworkGapClass.LOW_BANDWIDTH: NetworkActionType.COMPRESS,
            NetworkGapClass.PACKET_LOSS: NetworkActionType.SWITCH_PROTOCOL,
            NetworkGapClass.CONGESTION: NetworkActionType.ADD_CACHE,
            NetworkGapClass.PROTOCOL_MISMATCH: NetworkActionType.SWITCH_PROTOCOL,
        })
