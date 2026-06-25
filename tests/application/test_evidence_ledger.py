"""Unit tests for EvidenceLedger (M014 S04)."""

from __future__ import annotations

import pytest

from active_skill_system.application.evidence_ledger import (
    EvidenceEntry,
    EvidenceLedger,
)


def _entry(**overrides) -> EvidenceEntry:
    defaults = dict(
        patch_id="p1",
        action="add_node",
        expected="fact added",
        actual="fact added",
        verified_by="validator",
        accepted=True,
    )
    defaults.update(overrides)
    return EvidenceEntry(**defaults)


def test_entry_constructs() -> None:
    e = _entry()
    assert e.patch_id == "p1"
    assert e.accepted is True


def test_entry_rejects_empty_patch_id() -> None:
    with pytest.raises(ValueError, match="patch_id"):
        _entry(patch_id="")


def test_entry_rejects_empty_action() -> None:
    with pytest.raises(ValueError, match="action"):
        _entry(action="")


def test_entry_rejects_empty_verified_by() -> None:
    with pytest.raises(ValueError, match="verified_by"):
        _entry(verified_by="")


def test_ledger_append_and_list_all() -> None:
    ledger = EvidenceLedger()
    ledger.append(_entry(patch_id="p1"))
    ledger.append(_entry(patch_id="p2"))
    assert len(ledger) == 2
    assert ledger.list_all()[0].patch_id == "p1"


def test_ledger_filter_by_patch() -> None:
    ledger = EvidenceLedger()
    ledger.append(_entry(patch_id="p1"))
    ledger.append(_entry(patch_id="p2"))
    ledger.append(_entry(patch_id="p1"))
    result = ledger.filter_by_patch("p1")
    assert len(result) == 2


def test_ledger_filter_by_accepted() -> None:
    ledger = EvidenceLedger()
    ledger.append(_entry(accepted=True))
    ledger.append(_entry(accepted=False))
    ledger.append(_entry(accepted=True))
    accepted = ledger.filter_by_accepted(True)
    rejected = ledger.filter_by_accepted(False)
    assert len(accepted) == 2
    assert len(rejected) == 1


def test_ledger_empty() -> None:
    ledger = EvidenceLedger()
    assert len(ledger) == 0
    assert ledger.list_all() == ()


def test_ledger_entry_is_frozen() -> None:
    e = _entry()
    with pytest.raises(Exception):
        e.patch_id = "modified"  # type: ignore[misc]
