"""L1 Domain - Claim lifecycle + anti-fantasy invariant (Cognitive Runtime).

A Claim is a factual assertion that moves through a lifecycle (concept.md §8,
architecture.md §6.2). The load-bearing guarantee of the whole system is:

> **A Claim cannot self-promote from PROPOSED to VERIFIED without independent
> grounding.** (concept.md §8: "LLM не может самостоятельно перевести своё
> утверждение из PROPOSED в VERIFIED".)

Grounding is provided by at least one of:
  - non-empty ``evidence_ids`` (an external source / evidence node), OR
  - a ``grounding_kind`` in ``LEGITIMATE_GROUNDING`` (deterministic computation
    or a registered rule).

Hypotheses are explicitly NOT grounding — marking a claim as a hypothesis is a
way to include it without asserting it as fact (anti-fantasy rule 4).

Pure domain. NO I/O, NO infrastructure imports (R002). Frozen dataclass with
``__post_init__`` invariant validation. stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class ClaimStatus(StrEnum):
    """Lifecycle status of a Claim (concept.md §8)."""

    PROPOSED = "proposed"
    GROUNDED = "grounded"  # evidence found
    VERIFIED = "verified"  # validator/independent mechanism passed
    HYPOTHESIS = "hypothesis"  # explicitly unverified assumption
    CONFLICTED = "conflicted"  # contradiction found
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class GroundingKind(StrEnum):
    """Independent mechanisms that may ground a claim (anti-fantasy rule 2-3)."""

    NONE = "none"
    EXTERNAL_EVIDENCE = "external_evidence"  # via evidence_ids
    DETERMINISTIC_COMPUTATION = "deterministic_computation"
    REGISTERED_RULE = "registered_rule"
    HUMAN_APPROVAL = "human_approval"


# Kinds that count as independent grounding for VERIFIED.
LEGITIMATE_GROUNDING = frozenset(
    {
        GroundingKind.EXTERNAL_EVIDENCE,
        GroundingKind.DETERMINISTIC_COMPUTATION,
        GroundingKind.REGISTERED_RULE,
        GroundingKind.HUMAN_APPROVAL,
    }
)


def _is_grounded(claim: Claim) -> bool:
    """True iff the claim has independent grounding (evidence OR legitimate kind)."""
    if claim.grounding_kind in LEGITIMATE_GROUNDING and claim.grounding_kind != GroundingKind.NONE:
        return True
    return len(claim.evidence_ids) > 0


@dataclass(frozen=True)
class Claim:
    """A factual assertion with a lifecycle status and grounding chain.

    Carries:
      - id: unique identifier (string, non-empty).
      - text: the assertion (non-empty).
      - status: one of ClaimStatus.
      - evidence_ids: tuple of ids that ground the claim (external sources /
        evidence nodes). Empty by default.
      - grounding_kind: how the claim is grounded (GroundingKind.NONE by
        default — i.e. NOT independently grounded).
      - created_at: UTC timestamp.

    Anti-fantasy invariant (enforced in ``with_status``): a transition to
    VERIFIED is REJECTED unless the claim is grounded (evidence_ids non-empty
    OR grounding_kind in LEGITIMATE_GROUNDING). The constructor only blocks a
    *direct* construction of an ungrounded VERIFIED claim; ``with_status`` is
    the controlled transition that callers must use.
    """

    id: str
    text: str
    status: ClaimStatus = ClaimStatus.PROPOSED
    evidence_ids: tuple[str, ...] = ()
    grounding_kind: GroundingKind = GroundingKind.NONE
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.id, str) or not self.id.strip():
            errors.append(f"id must be a non-empty string (got {self.id!r})")
        if not isinstance(self.text, str) or not self.text.strip():
            errors.append(f"text must be a non-empty string (got {self.text!r})")
        if not isinstance(self.status, ClaimStatus):
            errors.append(f"status must be a ClaimStatus (got {type(self.status).__name__})")
        if not isinstance(self.grounding_kind, GroundingKind):
            errors.append(
                f"grounding_kind must be a GroundingKind (got {type(self.grounding_kind).__name__})"
            )
        # Anti-fantasy: an ungrounded VERIFIED claim is forbidden even at
        # construction. A grounded one is allowed.
        if self.status is ClaimStatus.VERIFIED and not _is_grounded(self):
            errors.append(
                "anti-fantasy violation: Claim with status VERIFIED requires grounding "
                "(non-empty evidence_ids OR grounding_kind in LEGITIMATE_GROUNDING)"
            )
        if errors:
            raise ValueError(f"Claim({self.id!r}) invariant violation: " + "; ".join(errors))

    @property
    def grounded(self) -> bool:
        """Whether this claim has independent grounding."""
        return _is_grounded(self)

    def with_status(self, status: ClaimStatus) -> Claim:
        """Return a new Claim with the given status, enforcing the anti-fantasy gate.

        Raises ValueError on an illegal promotion to VERIFIED without grounding.
        """
        if status is ClaimStatus.VERIFIED and not _is_grounded(self):
            raise ValueError(
                f"anti-fantasy violation: Claim({self.id!r}) cannot be promoted to VERIFIED "
                "without grounding (set evidence_ids or a legitimate grounding_kind first)"
            )
        return Claim(
            id=self.id,
            text=self.text,
            status=status,
            evidence_ids=self.evidence_ids,
            grounding_kind=self.grounding_kind,
            created_at=self.created_at,
        )
