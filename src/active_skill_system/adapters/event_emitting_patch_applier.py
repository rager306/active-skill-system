"""L3 Adapter — EventEmittingPatchApplier (M053 S10, Wave C audit trail).

Wraps InMemoryPatchApplier to emit GraphEvents for patch lifecycle:
  - patch.proposed (when a behavior proposes a patch)
  - patch.approved (when a policy approves)
  - patch.rejected (when a policy rejects)
  - patch.applied (when an approved patch is applied)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from active_skill_system.adapters.inmemory_patch_applier import InMemoryPatchApplier
from active_skill_system.application.ports.event_store import EventStore
from active_skill_system.domain.graph_primitives import GraphEvent

logger = logging.getLogger(__name__)


class EventEmittingPatchApplier(InMemoryPatchApplier):
    """PatchApplier that emits GraphEvents for all patch lifecycle transitions."""

    def __init__(self, event_store: EventStore, apply_fn: Callable[[Any], None] | None = None) -> None:
        super().__init__(apply_fn=apply_fn)
        if event_store is None:
            raise TypeError("event_store must be a non-None EventStore")
        self._store = event_store
        self._event_counter = 0

    def propose(self, proposed_by: str, patch: Any, reason: str = "") -> Any:
        proposal = super().propose(proposed_by, patch, reason)
        self._emit_event("patch.proposed", "", {
            "proposal_id": proposal.id,
            "proposed_by": proposed_by,
            "reason": reason,
        })
        return proposal

    def approve(self, proposal_id: str, reviewed_by: str = "", reason: str = "") -> Any:
        proposal = super().approve(proposal_id, reviewed_by, reason)
        self._emit_event("policy.approved", "", {
            "proposal_id": proposal_id,
            "reviewed_by": reviewed_by,
            "reason": reason,
        })
        return proposal

    def reject(self, proposal_id: str, reviewed_by: str = "", reason: str = "") -> Any:
        proposal = super().reject(proposal_id, reviewed_by, reason)
        self._emit_event("policy.rejected", "", {
            "proposal_id": proposal_id,
            "reviewed_by": reviewed_by,
            "reason": reason,
        })
        return proposal

    def apply(self, proposal_id: str) -> Any:
        proposal = super().apply(proposal_id)
        self._emit_event("patch.applied", "", {
            "proposal_id": proposal_id,
            "proposed_by": proposal.proposed_by,
        })
        return proposal

    def _emit_event(self, event_type: str, run_id: str, payload: dict[str, Any]) -> None:
        """Emit a GraphEvent to the EventStore."""
        self._event_counter += 1
        try:
            self._store.append(GraphEvent(
                id=f"{event_type}.{self._event_counter}",
                type=event_type,
                payload=payload,
                actor="patch_applier",
                run_id=run_id,
                timestamp_ns=self._event_counter,
            ))
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to emit event %s: %s", event_type, e)
