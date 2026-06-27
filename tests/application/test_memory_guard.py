"""Tests for memory_guard (M040 S03 T04)."""

from __future__ import annotations

import pytest

from active_skill_system.application.use_cases import memory_guard


def test_check_memory_returns_bool():
    assert isinstance(memory_guard.check_memory(threshold_pct=95.0), bool)


def test_check_memory_never_raises_on_unknown_pressure(monkeypatch):
    """When psutil absent and resource undeterminable, guard must not raise."""
    monkeypatch.setattr(memory_guard, "system_memory_pressure_pct", lambda: None)
    monkeypatch.setattr(memory_guard, "process_rss_bytes", lambda: None)
    assert memory_guard.check_memory(threshold_pct=50.0) is True  # safe default


def test_check_memory_blocks_above_threshold(monkeypatch):
    monkeypatch.setattr(memory_guard, "system_memory_pressure_pct", lambda: 95.0)
    assert memory_guard.check_memory(threshold_pct=90.0) is False


def test_check_memory_allows_below_threshold(monkeypatch):
    monkeypatch.setattr(memory_guard, "system_memory_pressure_pct", lambda: 40.0)
    assert memory_guard.check_memory(threshold_pct=90.0) is True


def test_check_memory_boundary(monkeypatch):
    monkeypatch.setattr(memory_guard, "system_memory_pressure_pct", lambda: 90.0)
    # exactly at threshold is NOT ok (strictly less).
    assert memory_guard.check_memory(threshold_pct=90.0) is False


def test_check_memory_rejects_invalid_threshold():
    with pytest.raises(ValueError):
        memory_guard.check_memory(threshold_pct=0.0)
    with pytest.raises(ValueError):
        memory_guard.check_memory(threshold_pct=150.0)


def test_process_rss_bytes_returns_int_or_none():
    rss = memory_guard.process_rss_bytes()
    assert rss is None or isinstance(rss, int)


def test_system_pressure_returns_float_or_none():
    p = memory_guard.system_memory_pressure_pct()
    assert p is None or (isinstance(p, float) and 0.0 <= p <= 100.0)


def test_psutil_absent_falls_back_gracefully(monkeypatch):
    """Simulate psutil missing: importlib raises ImportError, guard degrades."""
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("no psutil")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    # Should not raise; pressure returns None, guard returns True (safe default).
    assert memory_guard.system_memory_pressure_pct() is None
