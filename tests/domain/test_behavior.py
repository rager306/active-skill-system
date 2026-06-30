"""Tests for M053 S00 — Behavior + EventMatcher domain types."""

from __future__ import annotations

import pytest

from active_skill_system.domain.behavior import Behavior, BehaviorKind, EventMatcher

# ── EventMatcher ───────────────────────────────────────────────────────────


def test_event_matcher_accepts_single_type() -> None:
    m = EventMatcher(event_types=("claim.created",))
    assert m.matches("claim.created")
    assert not m.matches("evidence.linked")


def test_event_matcher_accepts_multiple_types() -> None:
    m = EventMatcher(event_types=("claim.created", "claim.updated"))
    assert m.matches("claim.created")
    assert m.matches("claim.updated")
    assert not m.matches("claim.deleted")


def test_event_matcher_payload_filter_matches() -> None:
    m = EventMatcher(event_types=("alert",), payload_filter={"severity": "high"})
    assert m.matches("alert", {"severity": "high", "msg": "x"})
    assert not m.matches("alert", {"severity": "low"})


def test_event_matcher_payload_filter_no_payload() -> None:
    m = EventMatcher(event_types=("alert",), payload_filter={"severity": "high"})
    assert not m.matches("alert", None)


def test_event_matcher_empty_payload_filter_matches_any() -> None:
    m = EventMatcher(event_types=("evt",))
    assert m.matches("evt", {})
    assert m.matches("evt", {"any": "thing"})
    assert m.matches("evt", None)


def test_event_matcher_rejects_empty_types() -> None:
    with pytest.raises(ValueError, match="event_types must be non-empty"):
        EventMatcher(event_types=())


def test_event_matcher_rejects_non_string_type() -> None:
    with pytest.raises(ValueError, match="event_type must be non-empty"):
        EventMatcher(event_types=("",))  # type: ignore[arg-type]


# ── Behavior ───────────────────────────────────────────────────────────────


def test_behavior_creation_defaults() -> None:
    m = EventMatcher(event_types=("claim.created",))
    b = Behavior(name="evidence_check", matcher=m)
    assert b.name == "evidence_check"
    assert b.kind == BehaviorKind.EVENT
    assert b.activate_after == 0
    assert b.description == ""


def test_behavior_creation_full() -> None:
    m = EventMatcher(event_types=("graph.changed",))
    b = Behavior(name="gap_detector", matcher=m, kind=BehaviorKind.PATTERN,
                 activate_after=5, description="Detects gaps")
    assert b.kind == BehaviorKind.PATTERN
    assert b.activate_after == 5
    assert b.description == "Detects gaps"


def test_behavior_rejects_empty_name() -> None:
    m = EventMatcher(event_types=("evt",))
    with pytest.raises(ValueError, match="name must be non-empty"):
        Behavior(name="", matcher=m)


def test_behavior_rejects_bad_kind() -> None:
    m = EventMatcher(event_types=("evt",))
    with pytest.raises(ValueError, match="kind must be"):
        Behavior(name="b", matcher=m, kind="invalid")


def test_behavior_rejects_negative_activate_after() -> None:
    m = EventMatcher(event_types=("evt",))
    with pytest.raises(ValueError, match="activate_after must be non-negative"):
        Behavior(name="b", matcher=m, activate_after=-1)


def test_behavior_should_activate_immediate() -> None:
    m = EventMatcher(event_types=("evt",))
    b = Behavior(name="b", matcher=m, activate_after=0)
    assert b.should_activate(0)
    assert b.should_activate(10)


def test_behavior_should_activate_delayed() -> None:
    m = EventMatcher(event_types=("evt",))
    b = Behavior(name="b", matcher=m, activate_after=5)
    assert not b.should_activate(4)
    assert b.should_activate(5)
    assert b.should_activate(100)


def test_behavior_matches_delegates_to_matcher() -> None:
    m = EventMatcher(event_types=("claim.created",), payload_filter={"severity": "high"})
    b = Behavior(name="b", matcher=m)
    assert b.matches("claim.created", {"severity": "high"})
    assert not b.matches("claim.created", {"severity": "low"})
    assert not b.matches("other.event")


def test_behavior_kind_constants() -> None:
    assert BehaviorKind.EVENT == "event"
    assert BehaviorKind.PATTERN == "pattern"
    assert BehaviorKind.RELATION == "relation"
    assert BehaviorKind.SCHEDULED == "scheduled"
