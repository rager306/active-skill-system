"""L2 Application — PolicyGate use case (M053 S04, Wave C primitive #8).

Evaluates proposed patches against registered policies. If a policy matches
and decides APPROVED, the patch is approved via PatchApplier. If REJECTED,
the patch is rejected. If no policy matches, the patch stays PENDING
(manual review needed).

This is the gate between behavior proposal and patch execution. Behaviors
propose patches; PolicyGate decides which patches apply.
"""

from __future__ import annotations

from active_skill_system.application.ports.patch_applier import (
    PatchApplier,
    PatchProposal,
)
from active_skill_system.domain.policy import (
    Policy,
    PolicyDecision,
    PolicyEvaluation,
    PolicyRule,
)


class PolicyGate:
    """Evaluates patches against registered policies.

    Usage:
        gate = PolicyGate(patch_applier)
        gate.register(Policy(name="safe", rule=PolicyRule.AUTO_APPROVE))
        evaluation = gate.evaluate(proposal)
        # If approved, PatchApplier.approve() was called automatically.
    """

    def __init__(self, applier: PatchApplier) -> None:
        if applier is None:
            raise TypeError("applier must be a non-None PatchApplier")
        self._applier = applier
        self._policies: list[Policy] = []

    def register(self, policy: Policy) -> None:
        """Register a policy. Higher priority policies are evaluated first."""
        if not isinstance(policy, Policy):
            raise TypeError(f"policy must be a Policy (got {type(policy).__name__})")
        self._policies.append(policy)
        # Sort by priority descending (highest priority first).
        self._policies.sort(key=lambda p: p.priority, reverse=True)

    def evaluate(self, proposal: PatchProposal) -> PolicyEvaluation:
        """Evaluate a proposal against all matching policies.

        Returns the first matching policy's decision. If no policy matches,
        returns PENDING (manual review needed).

        If a policy decides APPROVED, the proposal is auto-approved in the
        PatchApplier. If REJECTED, it's auto-rejected.
        """
        for policy in self._policies:
            if not policy.matches_patch(proposal.patch):
                continue

            decision = self._apply_rule(policy, proposal)

            if decision.decision == PolicyDecision.APPROVED:
                self._applier.approve(
                    proposal.id,
                    reviewed_by=policy.name,
                    reason=decision.reason,
                )
                return PolicyEvaluation(
                    decision=PolicyDecision.APPROVED,
                    policy_name=policy.name,
                    reason=decision.reason,
                    patch_id=proposal.id,
                )
            elif decision.decision == PolicyDecision.REJECTED:
                self._applier.reject(
                    proposal.id,
                    reviewed_by=policy.name,
                    reason=decision.reason,
                )
                return PolicyEvaluation(
                    decision=PolicyDecision.REJECTED,
                    policy_name=policy.name,
                    reason=decision.reason,
                    patch_id=proposal.id,
                )

        # No policy matched → pending (manual review).
        return PolicyEvaluation(
            decision=PolicyDecision.PENDING,
            policy_name="",
            reason="No matching policy; manual review required",
            patch_id=proposal.id,
        )

    def evaluate_all_pending(self) -> list[PolicyEvaluation]:
        """Evaluate all pending proposals. Returns list of evaluations."""
        results: list[PolicyEvaluation] = []
        for proposal in self._applier.list_pending():
            results.append(self.evaluate(proposal))
        return results

    def list_policies(self) -> list[Policy]:
        """List registered policies (for debugging)."""
        return list(self._policies)

    def _apply_rule(self, policy: Policy, proposal: PatchProposal) -> PolicyEvaluation:
        """Apply a policy rule to a proposal. Returns the decision."""
        if policy.rule == PolicyRule.AUTO_APPROVE:
            return PolicyEvaluation(
                decision=PolicyDecision.APPROVED,
                policy_name=policy.name,
                reason=f"Auto-approved by {policy.name}",
            )
        if policy.rule == PolicyRule.AUTO_REJECT:
            return PolicyEvaluation(
                decision=PolicyDecision.REJECTED,
                policy_name=policy.name,
                reason=f"Auto-rejected by {policy.name}",
            )
        if policy.rule == PolicyRule.MANUAL_REVIEW:
            return PolicyEvaluation(
                decision=PolicyDecision.PENDING,
                policy_name=policy.name,
                reason=f"Manual review required by {policy.name}",
            )
        if policy.rule == PolicyRule.MEASURABLE_IMPROVEMENT:
            # Check if the patch claims measurable improvement (in reason).
            if "improvement" in proposal.reason.lower():
                return PolicyEvaluation(
                    decision=PolicyDecision.APPROVED,
                    policy_name=policy.name,
                    reason=f"Measurable improvement claimed by {proposal.proposed_by}",
                )
            return PolicyEvaluation(
                decision=PolicyDecision.REJECTED,
                policy_name=policy.name,
                reason="No measurable improvement detected",
            )
        # Unknown rule → pending.
        return PolicyEvaluation(
            decision=PolicyDecision.PENDING,
            policy_name=policy.name,
            reason=f"Unknown rule {policy.rule}",
        )
