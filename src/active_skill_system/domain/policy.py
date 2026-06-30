"""L1 Domain — Policy (M053 S04, Wave C primitive #8).

A Policy is a rule that gates whether a proposed patch is approved or
rejected. Policies are evaluated by the PolicyGate use case (application
layer) when a behavior proposes a patch.

This mirrors activegraph's Policy + approval.proposed/approve model:
patches are proposed, policies evaluate them, and the patch is applied
(or rejected) based on policy decisions.

Pure domain. NO I/O, NO infrastructure imports (R002/R003). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class PolicyDecision(StrEnum):
    """The decision a policy makes about a proposed patch."""

    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"       # needs manual review (no auto policy matched)


class PolicyRule(StrEnum):
    """Built-in policy rules (extensible via custom rules in S08 presets)."""

    AUTO_APPROVE = "auto_approve"        # always approve (safe patches)
    AUTO_REJECT = "auto_reject"          # always reject (dangerous patches)
    MEASURABLE_IMPROVEMENT = "measurable_improvement"  # approve if graph improves
    MANUAL_REVIEW = "manual_review"      # needs human approval


@dataclass(frozen=True)
class Policy:
    """A named policy rule that gates proposed patches.

    Fields:
      - name: unique policy identifier (e.g. "safe_add_node").
      - rule: PolicyRule (how this policy decides).
      - description: human-readable purpose.
      - priority: evaluation order (higher = evaluated first, default 0).
      - patch_filter: dict of attributes to match against the patch
        (e.g. {"op_type": "add_node"} — only evaluate patches matching this).
        Empty dict = match all patches.

    The evaluation logic lives in the application PolicyGate use case,
    not here. This domain type describes the policy SPEC.
    """

    name: str
    rule: PolicyRule
    description: str = ""
    priority: int = 0
    patch_filter: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.name, str) or not self.name.strip():
            errors.append(f"name must be non-empty string (got {self.name!r})")
        if not isinstance(self.rule, PolicyRule):
            errors.append(f"rule must be PolicyRule (got {type(self.rule).__name__})")
        if not isinstance(self.priority, int):
            errors.append(f"priority must be int (got {type(self.priority).__name__})")
        if self.patch_filter is None:
            object.__setattr__(self, "patch_filter", {})
        if not isinstance(self.description, str):
            errors.append(f"description must be string (got {type(self.description).__name__})")
        if errors:
            raise ValueError("Policy invariant violation: " + "; ".join(errors))

    def matches_patch(self, patch: Any) -> bool:
        """Check if this policy applies to the given patch.

        A policy applies if all patch_filter key-value pairs match
        attributes on the patch. If patch_filter is empty, matches all.

        Args:
            patch: the proposed patch (GraphPatch or dict).

        Returns:
            True if this policy should evaluate this patch.
        """
        if not self.patch_filter:
            return True

        # Try dict-like access first, then attribute access.
        patch_dict = patch if isinstance(patch, dict) else getattr(patch, "__dict__", {})
        for key, expected in self.patch_filter.items():
            actual = patch_dict.get(key)
            if actual != expected:
                return False
        return True


@dataclass(frozen=True)
class PolicyEvaluation:
    """The result of evaluating a patch against policies.

    Fields:
      - decision: APPROVED, REJECTED, or PENDING.
      - policy_name: which policy made the decision (empty if PENDING).
      - reason: human-readable rationale.
      - patch_id: the proposal ID that was evaluated.
    """

    decision: PolicyDecision
    policy_name: str = ""
    reason: str = ""
    patch_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.decision, PolicyDecision):
            raise ValueError(
                f"decision must be PolicyDecision (got {type(self.decision).__name__})"
            )
