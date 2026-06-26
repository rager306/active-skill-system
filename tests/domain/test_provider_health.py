"""Tests for ProviderHealth (M038 S01 T02)."""

from __future__ import annotations

import pytest

from active_skill_system.domain.provider_health import ProviderHealth


def test_defaults_are_healthy():
    h = ProviderHealth(provider_id="router")
    assert h.consecutive_failures == 0
    assert h.last_error is None
    assert h.last_success_at is None
    assert h.is_healthy() is True


def test_record_failure_increments_and_stores_error():
    h = ProviderHealth(provider_id="router")
    h2 = h.record_failure("timeout")
    assert h2.consecutive_failures == 1
    assert h2.last_error == "timeout"
    # Original is unchanged (immutable).
    assert h.consecutive_failures == 0


def test_record_failure_accumulates():
    h = ProviderHealth(provider_id="router")
    h = h.record_failure("a")
    h = h.record_failure("b")
    assert h.consecutive_failures == 2
    assert h.last_error == "b"


def test_record_success_resets_and_timestamps():
    h = ProviderHealth(provider_id="router", consecutive_failures=2, last_error="boom")
    h2 = h.record_success(now=42.0)
    assert h2.consecutive_failures == 0
    assert h2.last_error is None
    assert h2.last_success_at == 42.0


def test_is_healthy_threshold_boundary():
    h = ProviderHealth(provider_id="router", consecutive_failures=2)
    assert h.is_healthy(max_failures=3) is True
    h = h.record_failure("x")
    assert h.consecutive_failures == 3
    assert h.is_healthy(max_failures=3) is False


def test_is_healthy_custom_threshold():
    h = ProviderHealth(provider_id="router", consecutive_failures=1)
    assert h.is_healthy(max_failures=1) is False


def test_immutable_frozen():
    from dataclasses import FrozenInstanceError

    h = ProviderHealth(provider_id="router")
    with pytest.raises(FrozenInstanceError):
        h.consecutive_failures = 5  # type: ignore[misc]


def test_invalid_provider_id_rejected():
    with pytest.raises(ValueError):
        ProviderHealth(provider_id="")


def test_negative_failures_rejected():
    with pytest.raises(ValueError):
        ProviderHealth(provider_id="router", consecutive_failures=-1)


def test_empty_error_rejected_by_record_failure():
    h = ProviderHealth(provider_id="router")
    with pytest.raises(ValueError):
        h.record_failure("")


def test_invalid_max_failures_rejected():
    h = ProviderHealth(provider_id="router")
    with pytest.raises(ValueError):
        h.is_healthy(max_failures=0)
