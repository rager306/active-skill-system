"""L3 Adapter — InMemoryPatchApplier (M053 S03, Wave C primitive #5).

In-memory implementation of PatchApplier. Stores proposals in a dict,
enforces the propose → approve/reject → apply lifecycle.

The actual patch execution (applying GraphPatch to a graph) is delegated
to a callable provided at construction time. This keeps the adapter focused
on lifecycle management while letting the composition layer wire the real
graph mutation.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from active_skill_system.application.ports.patch_applier import (
    PatchApplier,
    PatchProposal,
)


class InMemoryPatchApplier:
    """In-memory PatchApplier with propose/approve/reject/apply lifecycle.

    Args:
        apply_fn: callable that takes a GraphPatch and applies it to the graph.
            Called when a proposal is applied. If None, patches are tracked
            but not executed (useful for testing the lifecycle without a graph).
    """

    def __init__(self, apply_fn: Callable[[Any], None] | None = None) -> None:
        self._proposals: dict[str, PatchProposal] = {}
        self._apply_fn = apply_fn

    def propose(self, proposed_by: str, patch: Any, reason: str = "") -> PatchProposal:
        """Propose a patch. Returns a PatchProposal with status='pending'."""
        proposal = PatchProposal(
            id=f"patch-{uuid.uuid4().hex[:8]}",
            proposed_by=proposed_by,
            patch=patch,
            reason=reason,
        )
        self._proposals[proposal.id] = proposal
        return proposal

    def approve(self, proposal_id: str, reviewed_by: str = "", reason: str = "") -> PatchProposal:
        """Approve a pending proposal."""
        proposal = self._require(proposal_id)
        if proposal.status != "pending":
            raise ValueError(
                f"Cannot approve proposal {proposal_id} with status {proposal.status!r}"
            )
        updated = proposal.with_status("approved", reviewed_by, reason)
        self._proposals[proposal_id] = updated
        return updated

    def reject(self, proposal_id: str, reviewed_by: str = "", reason: str = "") -> PatchProposal:
        """Reject a pending proposal."""
        proposal = self._require(proposal_id)
        if proposal.status != "pending":
            raise ValueError(
                f"Cannot reject proposal {proposal_id} with status {proposal.status!r}"
            )
        updated = proposal.with_status("rejected", reviewed_by, reason)
        self._proposals[proposal_id] = updated
        return updated

    def apply(self, proposal_id: str) -> PatchProposal:
        """Apply an approved proposal. Executes the patch via apply_fn."""
        proposal = self._require(proposal_id)
        if proposal.status != "approved":
            raise ValueError(
                f"Cannot apply proposal {proposal_id} with status {proposal.status!r} "
                f"(must be 'approved')"
            )
        if self._apply_fn is not None:
            self._apply_fn(proposal.patch)
        updated = proposal.with_status("applied", proposal.reviewed_by, proposal.review_reason)
        self._proposals[proposal_id] = updated
        return updated

    def list_pending(self) -> list[PatchProposal]:
        """List all pending proposals."""
        return [p for p in self._proposals.values() if p.status == "pending"]

    def get(self, proposal_id: str) -> PatchProposal | None:
        """Get a proposal by ID."""
        return self._proposals.get(proposal_id)

    def list_all(self) -> list[PatchProposal]:
        """List all proposals (for debugging)."""
        return list(self._proposals.values())

    def _require(self, proposal_id: str) -> PatchProposal:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise KeyError(f"PatchProposal not found: {proposal_id}")
        return proposal


# InMemoryPatchApplier structurally satisfies PatchApplier.
assert isinstance(
    InMemoryPatchApplier(),  # type: ignore[arg-type]
    PatchApplier,
)
