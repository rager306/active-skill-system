"""Unit tests for scripts/risk_delta.compute_risk_delta (R013).

Pure-function tests on mock data — no subprocess, no real riskratchet. Cover:
increase, decrease, added, removed, top_n truncation, and delta==0 filtering.
"""

from __future__ import annotations

from active_skill_system.scripts.risk_delta import compute_risk_delta


def test_detect_increase_and_decrease() -> None:
    """Score 5→8 is an increase (delta=3); 8→5 is a decrease (delta=-3)."""
    baseline = [
        {"path": "a.py", "qualname": "f_up", "score": 5.0},
        {"path": "a.py", "qualname": "f_down", "score": 8.0},
    ]
    scan = [
        {"path": "a.py", "qualname": "f_up", "score": 8.0},
        {"path": "a.py", "qualname": "f_down", "score": 5.0},
    ]
    result = compute_risk_delta(baseline, scan, top_n=3)

    assert len(result["increases"]) == 1
    inc = result["increases"][0]
    assert inc["qualname"] == "f_up"
    assert inc["delta"] == 3.0
    assert inc["before"] == 5.0
    assert inc["after"] == 8.0

    assert len(result["decreases"]) == 1
    dec = result["decreases"][0]
    assert dec["qualname"] == "f_down"
    assert dec["delta"] == -3.0


def test_added_and_removed_and_unchanged() -> None:
    """A function only in scan is 'added'; only in baseline is 'removed';
    identical score is dropped from both increases and decreases."""
    baseline = [
        {"path": "a.py", "qualname": "kept", "score": 4.0},
        {"path": "a.py", "qualname": "gone", "score": 9.0},
    ]
    scan = [
        {"path": "a.py", "qualname": "kept", "score": 4.0},
        {"path": "a.py", "qualname": "new", "score": 12.0},
    ]
    result = compute_risk_delta(baseline, scan, top_n=3)

    assert result["increases"] == []  # kept unchanged (delta 0) — filtered
    assert result["decreases"] == []

    added = result["added"]
    assert len(added) == 1 and added[0]["qualname"] == "new" and added[0]["score"] == 12.0

    removed = result["removed"]
    assert len(removed) == 1 and removed[0]["qualname"] == "gone" and removed[0]["score"] == 9.0


def test_top_n_truncation_and_sort() -> None:
    """Worst-first sorting + top_n cap; increases sorted desc, decreases asc."""
    baseline = [{"path": "a.py", "qualname": f"f{i}", "score": 0.0} for i in range(5)]
    scan = [{"path": "a.py", "qualname": f"f{i}", "score": float(i + 1)} for i in range(5)]
    result = compute_risk_delta(baseline, scan, top_n=2)

    assert [r["qualname"] for r in result["increases"]] == ["f4", "f3"]  # deltas 5,4
    assert len(result["increases"]) == 2  # truncated from 5
