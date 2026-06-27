"""Offline tests for MiniMaxProvider retry+backoff (M042A — finding #4).

Real-LLM tests surfaced that Diligence tool-loop calls failed with
llm.network_error (POST /v1/messages → 404 from the local proxy). The provider
had NO retry, so one transient blip became a behavior.failed. These tests prove
the retry floor works offline (mocked client) without depending on the live
gateway/proxy.
"""

from __future__ import annotations

from typing import Any

import pytest
from activegraph.llm.errors import LLMBehaviorError

from active_skill_system.adapters.llm.minimax import MiniMaxProvider


class _FakeResponse:
    def __init__(self, text: str = "PONG"):
        self.text = text


class _FlakyClient:
    """messages.create fails N times (network error) then succeeds."""

    def __init__(self, *, fail_n: int = 0, exc_cls=ConnectionError):
        self.fail_n = fail_n
        self.calls = 0
        self.exc_cls = exc_cls

    @property
    def messages(self):
        outer = self

        class _M:
            def create(inner, *, timeout, **kwargs):  # noqa: ANN001
                outer.calls += 1
                if outer.calls <= outer.fail_n:
                    raise outer.exc_cls("simulated network blip")
                return _FakeResponse()

        return _M()


def _provider_with_client(client, **kw: Any) -> MiniMaxProvider:
    return MiniMaxProvider(client=client, enable_thinking=False, **kw)


def _request_kwargs():
    return {
        "system": "s",
        "messages": [],
        "model": "m",
        "max_tokens": 8,
        "temperature": 0.0,
        "top_p": 1.0,
        "output_schema": None,
        "timeout_seconds": 1.0,
    }


def test_provider_has_retry_config():
    p = MiniMaxProvider(client=_FlakyClient(), enable_thinking=False)
    assert p._max_retries >= 1
    assert p._base_backoff > 0


def test_transient_error_is_retried_then_succeeds(monkeypatch):
    # No real sleeping in tests.
    monkeypatch.setattr("active_skill_system.adapters.llm.minimax._provider.time.sleep", lambda _s: None)
    client = _FlakyClient(fail_n=2)
    p = _provider_with_client(client, max_retries=3, base_backoff=0.0)
    # complete() needs an Anthropic-shaped response; _FlakyClient returns _FakeResponse.
    # We bypass complete() and call the retry helper directly to isolate retry logic.
    raw = p._call_with_retry(client, {"model": "m", "max_tokens": 8, "messages": []}, 1.0, "m")
    assert raw.text == "PONG"
    assert client.calls == 3  # 2 failed + 1 success


def test_permanent_error_not_retried(monkeypatch):
    """A non-transient error (e.g. ValueError) must raise immediately, no retry."""
    monkeypatch.setattr("active_skill_system.adapters.llm.minimax._provider.time.sleep", lambda _s: None)

    class _PermanentClient:
        calls = 0

        @property
        def messages(self):
            class _M:
                def create(inner, *, timeout, **kwargs):  # noqa: ANN001
                    _PermanentClient.calls += 1
                    raise ValueError("permanent: bad request shape")

            return _M()


    p = MiniMaxProvider(client=_PermanentClient(), enable_thinking=False, max_retries=3)
    with pytest.raises(LLMBehaviorError):
        p._call_with_retry(_PermanentClient(), {"model": "m"}, 1.0, "m")
    # Permanent → exactly one attempt, no retries.
    assert _PermanentClient.calls == 1


def test_retry_exhaustion_raises_after_max(monkeypatch):
    monkeypatch.setattr("active_skill_system.adapters.llm.minimax._provider.time.sleep", lambda _s: None)
    client = _FlakyClient(fail_n=99)  # always fails
    p = _provider_with_client(client, max_retries=2, base_backoff=0.0)
    with pytest.raises(LLMBehaviorError):
        p._call_with_retry(client, {"model": "m", "max_tokens": 8, "messages": []}, 1.0, "m")
    # max_retries + 1 total attempts.
    assert client.calls == 3


def test_retry_uses_exponential_backoff(monkeypatch):
    delays: list[float] = []
    monkeypatch.setattr(
        "active_skill_system.adapters.llm.minimax._provider.time.sleep", delays.append
    )
    client = _FlakyClient(fail_n=99)
    p = _provider_with_client(client, max_retries=3, base_backoff=0.1)
    with pytest.raises(LLMBehaviorError):
        p._call_with_retry(client, {"model": "m"}, 1.0, "m")
    # 3 retries → 3 sleeps growing: 0.1, 0.2, 0.4.
    assert len(delays) == 3
    assert delays == sorted(delays)
    assert delays[0] < delays[-1]


# ── recognizes_model override (cross-provider mismatch fix) ───────────


def test_recognizes_model_accepts_minimax_family():
    p = MiniMaxProvider(client=_FlakyClient(), enable_thinking=False)
    assert p.recognizes_model("minimax/MiniMax-M3")
    assert p.recognizes_model("minimax/MiniMax-M2.7-highspeed")
    assert p.recognizes_model("MiniMax-M3")
    assert p.recognizes_model("MiniMax-M2.7")


def test_recognizes_model_rejects_claude_family():
    """Without the override, the base class recognises only claude-* and the
    runtime silently fell back to claude-sonnet-4-5 (proxy 404). The override
    must flip this so the runtime keeps our default_model."""
    p = MiniMaxProvider(client=_FlakyClient(), enable_thinking=False)
    assert not p.recognizes_model("claude-sonnet-4-5")
    assert not p.recognizes_model("claude-haiku-4-5")


def test_default_model_self_recognized():
    """The provider must recognise its own default_model (else runtime fallback)."""
    p = MiniMaxProvider(client=_FlakyClient(), enable_thinking=False)
    assert p.recognizes_model(p.default_model)
