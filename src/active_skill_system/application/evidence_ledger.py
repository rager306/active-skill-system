"""L2 Application — EvidenceLedger (M014 S04).

Append-only per-patch audit trail. Every GraphPatch accept/reject records
what was expected, what actually happened, and who verified. Synapse FSV
(Full-State Verification) pattern adapted to our repair loop.

Immutable: entries cannot be mutated or removed. This is the audit trail
that addresses comprehension debt (D006 loop engineering): the human can
always trace what the system did and why.

Pure application. Depends on stdlib only (R002).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class EvidenceEntry:
    """One entry in the evidence ledger.

    Carries:
      - patch_id: the GraphPatch version or id.
      - action: what the patch did (e.g. "add_node", "add_edge").
      - expected: what was expected to happen.
      - actual: what actually happened.
      - verified_by: who verified (e.g. "validator", "tool_readback", "human").
      - accepted: True if the patch was accepted, False if rejected.
      - timestamp: UTC when the entry was recorded.
    """

    patch_id: str
    action: str
    expected: str
    actual: str
    verified_by: str
    accepted: bool
    timestamp: datetime = datetime.now(UTC)  # noqa: RUF009

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.patch_id, str) or not self.patch_id.strip():
            errors.append(f"patch_id must be a non-empty string (got {self.patch_id!r})")
        if not isinstance(self.action, str) or not self.action.strip():
            errors.append(f"action must be a non-empty string (got {self.action!r})")
        if not isinstance(self.verified_by, str) or not self.verified_by.strip():
            errors.append(f"verified_by must be a non-empty string (got {self.verified_by!r})")
        if errors:
            raise ValueError("EvidenceEntry invariant violation: " + "; ".join(errors))


class EvidenceLedger:
    """Append-only ledger of evidence entries.

    No mutation or removal of existing entries. ``append`` is the only write
    operation. Queries: ``list_all``, ``filter_by_patch``, ``filter_by_accepted``.
    """

    def __init__(self) -> None:
        self._entries: list[EvidenceEntry] = []

    def append(self, entry: EvidenceEntry) -> None:
        """Append an entry. Cannot modify or remove existing entries."""
        self._entries.append(entry)

    def list_all(self) -> tuple[EvidenceEntry, ...]:
        """Return all entries in insertion order."""
        return tuple(self._entries)

    def filter_by_patch(self, patch_id: str) -> tuple[EvidenceEntry, ...]:
        """Return entries for a specific patch id."""
        return tuple(e for e in self._entries if e.patch_id == patch_id)

    def filter_by_accepted(self, accepted: bool) -> tuple[EvidenceEntry, ...]:
        """Return entries matching the accepted flag."""
        return tuple(e for e in self._entries if e.accepted == accepted)

    def __len__(self) -> int:
        return len(self._entries)
