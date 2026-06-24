"""L3 adapter — MiniMax LLM provider via the Anthropic-compatible gateway.

Wires four concerns: auth (override ``_client()`` so the SDK uses the gateway's
``ANTHROPIC_AUTH_TOKEN`` Bearer + base URL, not the hard-required ``ANTHROPIC_API_KEY``);
thinking preservation (``_thinking.py``); token counting with fallback
(``_tokens.py``); env (``_env.py``). Public API re-exported in ``__init__.py``.
"""

from __future__ import annotations

import os
import time
from typing import Any

from activegraph.llm.anthropic import (
    AnthropicProvider,
    _classify_provider_exception,
    _extract_text,
    _extract_tool_calls,
    _message_to_anthropic,
    _parse_structured,
    _retry_after_seconds,
)
from activegraph.llm.errors import LLMBehaviorError
from activegraph.llm.types import LLMMessage as _AgLLMMessage, LLMResponse, ToolCall

from active_skill_system.adapters.llm.minimax._thinking import ThinkingTurnCache, _block_to_dict
from active_skill_system.adapters.llm.minimax._tokens import count_tokens_fallback
from active_skill_system.application.ports.llm import LLMMessage


class MiniMaxProvider(AnthropicProvider):
    """MiniMax via the Anthropic-compatible gateway, thinking-preserving."""

    def __init__(
        self, *, model: str | None = None, client=None, pricing=None, enable_thinking: bool = True
    ) -> None:
        super().__init__(client=client, pricing=pricing)
        self.default_model = model or os.environ.get("ANTHROPIC_MODEL", "MiniMax-M3")
        # MiniMax-M3 ships thinking OFF by default; adaptive turns it on so M3
        # actually reasons (and the thinking-preservation shim has blocks to keep).
        self._enable_thinking = enable_thinking and self.default_model.startswith("MiniMax-M3")
        self._cache = ThinkingTurnCache()

    @property
    def _turn_blocks(self) -> dict[str, list[dict[str, Any]]]:
        """Legacy accessor — exposes the cache's backing store for tests."""
        return self._cache.blocks

    def _client(self):
        if self._client_override is not None:
            return self._client_override
        from anthropic import Anthropic

        return Anthropic()  # SDK reads ANTHROPIC_AUTH_TOKEN (Bearer) + ANTHROPIC_BASE_URL

    def count_tokens(self, *, system: str, messages: list[LLMMessage], model: str) -> int:
        """Real gateway count_tokens with a chars/4 fallback (see ``_tokens.py``).

        The gateway can reject some tool-loop shapes; fall back so the
        runtime's pre-call cost gate always works.
        """
        try:
            return int(super().count_tokens(system=system, messages=messages, model=model))
        except Exception:  # noqa: BLE001 - fallback must always work
            return count_tokens_fallback(system=system, messages=messages, model=model)

    def _remember_turn(self, raw: Any) -> None:
        """Cache this response's full blocks under each tool-use id."""
        ids = [tc.id for tc in _extract_tool_calls(raw) if tc.id]
        if not ids:
            return
        blocks = [b for b in (_block_to_dict(x) for x in (getattr(raw, "content", None) or [])) if b]
        self._cache.remember(ids, blocks)

    def _restore_thinking(self, wire_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Swap rebuilt assistant tool-turns back to their cached full blocks."""
        return self._cache.restore(wire_messages)

    @staticmethod
    def _to_activegraph_messages(messages: list[LLMMessage]) -> list[_AgLLMMessage]:
        """Convert application-port LLMMessage values to activegraph's type.

        Lives here (L3 adapter) so the application layer (L2) stays
        infra-free (R002): use-cases construct ``LLMMessage`` from
        ``application.ports.llm``; only the adapter imports activegraph's
        equivalent.
        """
        converted = []
        for m in messages:
            tool_calls = tuple(
                ToolCall(id=tc.id, name=tc.name, args=dict(tc.args))
                for tc in m.tool_calls
            )
            converted.append(
                _AgLLMMessage(
                    role=m.role,
                    content=m.content,
                    tool_use_id=m.tool_call_id,
                    tool_name=m.tool_name,
                    tool_calls=tool_calls or None,
                )
            )
        return converted

    def complete(  # noqa: D401 - signature mirrors the Protocol
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        model: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        output_schema: type | None,
        timeout_seconds: float,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        client = self._client()
        ag_messages = self._to_activegraph_messages(messages)
        wire_messages = self._restore_thinking([_message_to_anthropic(m) for m in ag_messages])
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": int(max_tokens),
            "messages": wire_messages,
            "temperature": float(temperature),
        }
        if system:
            kwargs["system"] = system
        if top_p < 1.0:
            kwargs["top_p"] = float(top_p)
        if tools:
            kwargs["tools"] = list(tools)
        if self._enable_thinking:
            kwargs["thinking"] = {"type": "adaptive"}

        t0 = time.monotonic()
        try:
            raw = client.messages.create(timeout=timeout_seconds, **kwargs)
        except Exception as e:
            reason = _classify_provider_exception(e)
            extras: dict[str, Any] = {
                "model": model,
                "exception_type": type(e).__name__,
                "message": str(e),
            }
            ra = _retry_after_seconds(e)
            if ra is not None:
                extras["retry_after_seconds"] = ra
            raise LLMBehaviorError(reason, str(e), payload_extras=extras) from e
        latency = time.monotonic() - t0

        text = _extract_text(raw)
        tool_calls: list[ToolCall] = _extract_tool_calls(raw)
        parsed: Any = None
        if output_schema is not None and not tool_calls:
            parsed = _parse_structured(text, output_schema)

        in_tok = int(getattr(getattr(raw, "usage", None), "input_tokens", 0) or 0)
        out_tok = int(getattr(getattr(raw, "usage", None), "output_tokens", 0) or 0)
        cost = self.estimate_cost(input_tokens=in_tok, output_tokens=out_tok, model=model)

        self._remember_turn(raw)

        return LLMResponse(
            raw_text=text,
            parsed=parsed,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            latency_seconds=latency,
            model=getattr(raw, "model", model),
            finish_reason=str(getattr(raw, "stop_reason", "end_turn") or "end_turn"),
            seed=None,
            cache_hit=False,
            tool_calls=tool_calls or None,
            provider_meta={"thinking_preserved": bool(self._cache.blocks)},
        )
