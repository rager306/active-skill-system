"""Tests for M053 S04 — Policy domain type + PolicyGate use case."""

from __future__ import annotations

import pytest

from active_skill_system.adapters.inmemory_patch_applier import InMemoryPatchApplier
from active_skill_system.application.use_cases.policy_gate import PolicyGate
from active_skill_system.domain.policy import (
    Policy,
    PolicyDecision,
    PolicyEvaluation,
    PolicyRule,
)

# ── Policy domain type ─────────────────────────────────────────────────────


def test_policy_creation_defaults() -> None:
    p = Policy(name="safe", rule=PolicyRule.AUTO_APPROVE)
    assert p.name == "safe"
    assert p.rule == PolicyRule.AUTO_APPROVE
    assert p.priority == 0
    assert p.patch_filter == {}
    assert p.description == ""


def test_policy_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="name must be non-empty"):
        Policy(name="", rule=PolicyRule.AUTO_APPROVE)


def test_policy_rejects_bad_rule_type() -> None:
    with pytest.raises(ValueError, match="rule must be PolicyRule"):
        Policy(name="p", rule="not-a-rule")  # type: ignore[arg-type]


def test_policy_matches_patch_no_filter() -> None:
    p = Policy(name="all", rule=PolicyRule.AUTO_APPROVE)
    assert p.matches_patch({"any": "thing"})
    assert p.matches_patch({})


def test_policy_matches_patch_with_filter() -> None:
    p = Policy(
        name="add_only",
        rule=PolicyRule.AUTO_APPROVE,
        patch_filter={"op_type": "add_node"},
    )
    assert p.matches_patch({"op_type": "add_node"})
    assert not p.matches_patch({"op_type": "remove_node"})


def test_policy_rule_values() -> None:
    assert PolicyRule.AUTO_APPROVE == "auto_approve"
    assert PolicyRule.AUTO_REJECT == "auto_reject"
    assert PolicyRule.MEASURABLE_IMPROVEMENT == "measurable_improvement"
    assert PolicyRule.MANUAL_REVIEW == "manual_review"


def test_policy_decision_values() -> None:
    assert PolicyDecision.APPROVED == "approved"
    assert PolicyDecision.REJECTED == "rejected"
    assert PolicyDecision.PENDING == "pending"


# ── PolicyEvaluation ──────────────────────────────────────────────────────


def test_policy_evaluation_creation() -> None:
    ev = PolicyEvaluation(
        decision=PolicyDecision.APPROVED,
        policy_name="safe",
        reason="ok",
        patch_id="p1",
    )
    assert ev.decision == PolicyDecision.APPROVED
    assert ev.policy_name == "safe"


def test_policy_evaluation_rejects_bad_decision() -> None:
    with pytest.raises(ValueError, match="decision must be PolicyDecision"):
        PolicyEvaluation(decision="bad")  # type: ignore[arg-type]


# ── PolicyGate ─────────────────────────────────────────────────────────────


def test_policy_gate_rejects_none_applier() -> None:
    with pytest.raises(TypeError, match="applier must be a non-None"):
        PolicyGate(None)  # type: ignore[arg-type]


def test_policy_gate_register_rejects_non_policy() -> None:
    gate = PolicyGate(InMemoryPatchApplier())
    with pytest.raises(TypeError, match="policy must be a Policy"):
        gate.register("not-a-policy")  # type: ignore[arg-type]


def test_auto_approve_policy_approves_patch() -> None:
    applier = InMemoryPatchApplier()
    gate = PolicyGate(applier)
    gate.register(Policy(name="safe", rule=PolicyRule.AUTO_APPROVE))

    proposal = applier.propose("behavior", {"op": "add"})
    ev = gate.evaluate(proposal)

    assert ev.decision == PolicyDecision.APPROVED
    assert ev.policy_name == "safe"
    assert applier.get(proposal.id).status == "approved"  # type: ignore[union-attr]


def test_auto_reject_policy_rejects_patch() -> None:
    applier = InMemoryPatchApplier()
    gate = PolicyGate(applier)
    gate.register(Policy(name="danger", rule=PolicyRule.AUTO_REJECT))

    proposal = applier.propose("behavior", {"op": "remove"})
    ev = gate.evaluate(proposal)

    assert ev.decision == PolicyDecision.REJECTED
    assert applier.get(proposal.id).status == "rejected"  # type: ignore[union-attr]


def test_no_matching_policy_returns_pending() -> None:
    applier = InMemoryPatchApplier()
    gate = PolicyGate(applier)
    # Register a policy that only matches add_node patches.
    gate.register(Policy(
        name="add_only", rule=PolicyRule.AUTO_APPROVE,
        patch_filter={"op_type": "add_node"},
    ))

    # Propose a remove patch — doesn't match the filter.
    proposal = applier.propose("behavior", {"op_type": "remove"})
    ev = gate.evaluate(proposal)

    assert ev.decision == PolicyDecision.PENDING
    assert "manual review" in ev.reason.lower()
    assert applier.get(proposal.id).status == "pending"  # type: ignore[union-attr]


def test_priority_order_high_evaluated_first() -> None:
    applier = InMemoryPatchApplier()
    gate = PolicyGate(applier)

    # Low priority: auto-approve.
    gate.register(Policy(name="approve", rule=PolicyRule.AUTO_APPROVE, priority=1))
    # High priority: auto-reject.
    gate.register(Policy(name="reject", rule=PolicyRule.AUTO_REJECT, priority=10))

    proposal = applier.propose("behavior", {"op": "add"})
    ev = gate.evaluate(proposal)

    # High priority reject should win.
    assert ev.decision == PolicyDecision.REJECTED
    assert ev.policy_name == "reject"


def test_evaluate_all_pending() -> None:
    applier = InMemoryPatchApplier()
    gate = PolicyGate(applier)
    gate.register(Policy(name="safe", rule=PolicyRule.AUTO_APPROVE))

    p1 = applier.propose("b1", {"op": "add"})
    p2 = applier.propose("b2", {"op": "add"})

    results = gate.evaluate_all_pending()
    assert len(results) == 2
    assert all(r.decision == PolicyDecision.APPROVED for r in results)


def test_measurable_improvement_rule() -> None:
    applier = InMemoryPatchApplier()
    gate = PolicyGate(applier)
    gate.register(Policy(name="improve", rule=PolicyRule.MEASURABLE_IMPROVEMENT))

    # Patch with improvement in reason → approved.
    p1 = applier.propose("b", {}, "closes a gap, measurable improvement")
    ev1 = gate.evaluate(p1)
    assert ev1.decision == PolicyDecision.APPROVED

    # Patch without improvement → rejected.
    p2 = applier.propose("b", {}, "no reason")
    ev2 = gate.evaluate(p2)
    assert ev2.decision == PolicyDecision.REJECTED


def test_manual_review_rule() -> None:
    applier = InMemoryPatchApplier()
    gate = PolicyGate(applier)
    gate.register(Policy(name="review", rule=PolicyRule.MANUAL_REVIEW))

    proposal = applier.propose("b", {})
    ev = gate.evaluate(proposal)
    assert ev.decision == PolicyDecision.PENDING
    assert "manual review" in ev.reason.lower()


def test_list_policies() -> None:
    gate = PolicyGate(InMemoryPatchApplier())
    gate.register(Policy(name="p1", rule=PolicyRule.AUTO_APPROVE))
    gate.register(Policy(name="p2", rule=PolicyRule.AUTO_REJECT))
    assert len(gate.list_policies()) == 2
