"""Tests for M053 S03 — PatchApplier port + InMemoryPatchApplier."""

from __future__ import annotations

import pytest

from active_skill_system.adapters.inmemory_patch_applier import InMemoryPatchApplier
from active_skill_system.application.ports.patch_applier import (
    PatchApplier,
    PatchProposal,
)

# ── PatchProposal ──────────────────────────────────────────────────────────


def test_patch_proposal_creation() -> None:
    p = PatchProposal(id="p1", proposed_by="behavior_x", patch={"op": "add"})
    assert p.id == "p1"
    assert p.status == "pending"
    assert p.reason == ""


def test_patch_proposal_rejects_empty_id() -> None:
    with pytest.raises(ValueError, match="id must be non-empty"):
        PatchProposal(id="", proposed_by="b", patch={})


def test_patch_proposal_rejects_bad_status() -> None:
    with pytest.raises(ValueError, match="status must be"):
        PatchProposal(id="p1", proposed_by="b", patch={}, status="invalid")


def test_patch_proposal_with_status_immutable() -> None:
    p = PatchProposal(id="p1", proposed_by="b", patch={})
    approved = p.with_status("approved", "policy1", "looks good")
    assert p.status == "pending"  # original unchanged
    assert approved.status == "approved"
    assert approved.reviewed_by == "policy1"
    assert approved.review_reason == "looks good"


# ── InMemoryPatchApplier Protocol ─────────────────────────────────────────


def test_inmemory_patch_applier_satisfies_protocol() -> None:
    assert isinstance(InMemoryPatchApplier(), PatchApplier)  # type: ignore[arg-type]


# ── Propose ────────────────────────────────────────────────────────────────


def test_propose_creates_pending_proposal() -> None:
    applier = InMemoryPatchApplier()
    p = applier.propose("behavior_x", {"op": "add_node"})
    assert p.status == "pending"
    assert p.proposed_by == "behavior_x"
    assert p.id.startswith("patch-")
    assert len(applier.list_pending()) == 1


# ── Approve ────────────────────────────────────────────────────────────────


def test_approve_pending_proposal() -> None:
    applier = InMemoryPatchApplier()
    p = applier.propose("b", {})
    approved = applier.approve(p.id, "policy1", "safe")
    assert approved.status == "approved"
    assert approved.reviewed_by == "policy1"
    assert applier.list_pending() == []


def test_approve_non_pending_fails() -> None:
    applier = InMemoryPatchApplier()
    p = applier.propose("b", {})
    applier.approve(p.id)
    with pytest.raises(ValueError, match="Cannot approve"):
        applier.approve(p.id)


def test_approve_unknown_fails() -> None:
    applier = InMemoryPatchApplier()
    with pytest.raises(KeyError, match="not found"):
        applier.approve("nonexistent")


# ── Reject ─────────────────────────────────────────────────────────────────


def test_reject_pending_proposal() -> None:
    applier = InMemoryPatchApplier()
    p = applier.propose("b", {})
    rejected = applier.reject(p.id, "policy1", "too risky")
    assert rejected.status == "rejected"
    assert rejected.review_reason == "too risky"


# ── Apply ──────────────────────────────────────────────────────────────────


def test_apply_approved_proposal() -> None:
    applied: list = []
    applier = InMemoryPatchApplier(apply_fn=applied.append)
    p = applier.propose("b", {"op": "add"})
    applier.approve(p.id)
    result = applier.apply(p.id)
    assert result.status == "applied"
    assert len(applied) == 1
    assert applied[0] == {"op": "add"}


def test_apply_unapproved_fails() -> None:
    applier = InMemoryPatchApplier()
    p = applier.propose("b", {})
    with pytest.raises(ValueError, match="must be 'approved'"):
        applier.apply(p.id)


def test_apply_without_fn_still_works() -> None:
    """Apply works even without apply_fn (lifecycle tracking only)."""
    applier = InMemoryPatchApplier()  # no apply_fn
    p = applier.propose("b", {})
    applier.approve(p.id)
    result = applier.apply(p.id)
    assert result.status == "applied"


# ── Get ────────────────────────────────────────────────────────────────────


def test_get_existing() -> None:
    applier = InMemoryPatchApplier()
    p = applier.propose("b", {})
    assert applier.get(p.id) is not None
    assert applier.get(p.id).id == p.id  # type: ignore[union-attr]


def test_get_nonexistent() -> None:
    applier = InMemoryPatchApplier()
    assert applier.get("nope") is None


# ── Full lifecycle ─────────────────────────────────────────────────────────


def test_full_lifecycle_propose_approve_apply() -> None:
    applied: list = []
    applier = InMemoryPatchApplier(apply_fn=applied.append)

    # 1. Propose
    p = applier.propose("evidence_linker", {"op": "add_edge"}, "links evidence to claim")
    assert p.status == "pending"

    # 2. Approve
    approved = applier.approve(p.id, "auto_approve_policy", "measurable improvement")
    assert approved.status == "approved"

    # 3. Apply
    result = applier.apply(p.id)
    assert result.status == "applied"
    assert len(applied) == 1


def test_rejected_proposal_cannot_be_applied() -> None:
    applier = InMemoryPatchApplier()
    p = applier.propose("b", {})
    applier.reject(p.id)
    with pytest.raises(ValueError, match="must be 'approved'"):
        applier.apply(p.id)
