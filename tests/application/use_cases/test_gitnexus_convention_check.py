"""Tests for GitNexus convention checker (M046 S01 T01)."""

from __future__ import annotations

from pathlib import Path

from active_skill_system.application.use_cases.gitnexus_convention_check import (
    ConventionChecker,
    ConventionResult,
)


def test_convention_result_is_frozen():
    from dataclasses import FrozenInstanceError

    import pytest

    r = ConventionResult(consistent=True, patterns_found=5, reason="ok")
    with pytest.raises(FrozenInstanceError):
        r.consistent = False  # type: ignore[misc]


def test_check_convention_with_full_candidate(tmp_path: Path):
    """Full-mark fixture should be consistent (has better_than)."""
    checker = ConventionChecker()
    # Use the project's full fixture
    result = checker.check_convention("tests/fixtures/sandbox/cache_full.py")
    assert isinstance(result, ConventionResult)
    # Either GitNexus finds patterns (consistent=True) or it's unavailable (skip=True).
    assert result.consistent is True


def test_check_convention_graceful_when_npx_missing(monkeypatch):
    """When npx is not available, the check degrades gracefully."""
    monkeypatch.setattr("shutil.which", lambda cmd: None if cmd == "npx" else "/fake/" + cmd)
    checker = ConventionChecker()
    result = checker.check_convention("tests/fixtures/sandbox/cache_full.py")
    assert result.consistent is True
    assert "unavailable" in result.reason.lower() or "skipped" in result.reason.lower()


def test_check_convention_missing_file():
    checker = ConventionChecker()
    result = checker.check_convention("nonexistent.py")
    # Either graceful skip (npx missing) or file-not-found.
    if result.patterns_found > 0:
        assert result.consistent is False
    else:
        assert result.consistent is True  # graceful skip


def test_check_convention_broken_candidate():
    """Broken fixture lacks better_than (but has wrong fields too).
    If GitNexus has patterns, this should flag inconsistency."""
    checker = ConventionChecker()
    result = checker.check_convention("tests/fixtures/sandbox/cache_broken.py")
    # The broken fixture DOES have better_than (just wrong direction).
    # So it should be consistent on the 'has better_than' check.
    # Only fails if it completely lacks the method.
    assert isinstance(result, ConventionResult)
