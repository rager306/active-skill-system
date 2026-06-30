"""L2 Application — PatchApplier port (M053 S03, Wave C primitive #5).

The patch lifecycle port: behaviors propose patches, policies gate which
patches apply, the applier executes approved patches against the graph.

This is activegraph primitive #5 (Patches) in our hexagonal architecture.
Behaviors do NOT mutate the graph directly — they propose patches through
this port. The PolicyGate (S04) evaluates patches before they are applied.

The port wraps the existing domain/runtime/patch.py GraphPatch type,
adding the propose → review → apply lifecycle that activegraph has.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class PatchProposal:
    """A patch proposed by a behavior.

    Fields:
      - id: unique proposal ID.
      - proposed_by: behavior name that proposed this patch.
      - patch: the GraphPatch (domain/runtime/patch.py) to apply.
      - reason: human-readable rationale.
      - created_at: when proposed.
      - status: "pending" | "approved" | "rejected" | "applied".
      - reviewed_by: policy name that approved/rejected (empty if pending).
      - review_reason: why it was approved/rejected.
    """

    id: str
    proposed_by: str
    patch: Any  # GraphPatch — typed as Any to keep L2 infra-free
    reason: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    status: str = "pending"
    reviewed_by: str = ""
    review_reason: str = ""

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.id, str) or not self.id.strip():
            errors.append(f"id must be non-empty string (got {self.id!r})")
        if not isinstance(self.proposed_by, str) or not self.proposed_by.strip():
            errors.append(f"proposed_by must be non-empty string (got {self.proposed_by!r})")
        if self.status not in ("pending", "approved", "rejected", "applied"):
            errors.append(f"status must be pending/approved/rejected/applied (got {self.status!r})")
        if errors:
            raise ValueError("PatchProposal invariant violation: " + "; ".join(errors))

    def with_status(self, status: str, reviewed_by: str = "", reason: str = "") -> PatchProposal:
        """Return a new PatchProposal with updated status (immutable update)."""
        return PatchProposal(
            id=self.id,
            proposed_by=self.proposed_by,
            patch=self.patch,
            reason=self.reason,
            created_at=self.created_at,
            status=status,
            reviewed_by=reviewed_by,
            review_reason=reason,
        )


@runtime_checkable
class PatchApplier(Protocol):
    """Patch lifecycle port: propose → review → apply.

    Behaviors call propose() to suggest graph mutations. PolicyGate (S04)
    calls approve()/reject() to gate them. apply() executes approved patches.

    Patches that are not approved cannot be applied. This separates proposal
    (behavior) from execution (applier), with policy as the gate.
    """

    def propose(self, proposed_by: str, patch: Any, reason: str = "") -> PatchProposal:
        """Propose a patch. Returns a PatchProposal with status='pending'."""
        ...

    def approve(self, proposal_id: str, reviewed_by: str = "", reason: str = "") -> PatchProposal:
        """Approve a pending proposal. Returns the updated proposal."""
        ...

    def reject(self, proposal_id: str, reviewed_by: str = "", reason: str = "") -> PatchProposal:
        """Reject a pending proposal. Returns the updated proposal."""
        ...

    def apply(self, proposal_id: str) -> PatchProposal:
        """Apply an approved proposal. Returns the updated proposal (status='applied')."""
        ...

    def list_pending(self) -> list[PatchProposal]:
        """List all pending proposals (not yet reviewed)."""
        ...

    def get(self, proposal_id: str) -> PatchProposal | None:
        """Get a proposal by ID. Returns None if not found."""
        ...
