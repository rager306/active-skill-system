"""L3 adapter — MiniMax LLM provider via the Anthropic-compatible gateway,
with thinking-preservation for multi-turn tool loops.

Implements the application's LLM port (structurally: activegraph's LLMProvider)
backed by MiniMax through https://api.minimax.io/anthropic.

Two concerns handled here:

1. Auth (why we subclass AnthropicProvider): AnthropicProvider hard-requires
   ANTHROPIC_API_KEY, but the MiniMax gateway authenticates with
   ANTHROPIC_AUTH_TOKEN (Bearer). We override `_client()` so the anthropic SDK
   picks up the Bearer token + base URL instead.

2. Thinking preservation (why we override complete()): activegraph rebuilds a
   tool-loop assistant turn from `raw_text + tool_calls` and DROPS the
   `thinking` blocks (LLMMessage.content is a str; `_message_to_anthropic`
   emits only [text, tool_use]). MiniMax-M3 uses interleaved thinking and the
   Anthropic spec ("preserving-thinking-blocks") requires the full content
   list (incl. thinking with its signature) to be echoed back, or the gateway
   rejects the tool result with error 2013 "tool result's tool id not found".

   Fix (provider-level, no activegraph patch): the provider remembers each
   response's full raw.content blocks, keyed by tool_use_id, and on the next
   turn replaces the rebuilt assistant turn with the cached full content. See
   `tests/test_minimax_provider.py` and the `activegraph` skill findings gap 5.1.
"""

from __future__ import annotations

import os
import time
from collections import OrderedDict
from pathlib import Path
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
from activegraph.llm.types import LLMMessage, LLMResponse, ToolCall
from dotenv import load_dotenv


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return here.parents[3]


PROJECT_ROOT = _project_root()
ENV_PATH = PROJECT_ROOT / ".env"


def load_env(env_path: Path | str = ENV_PATH) -> os._Environ:
    load_dotenv(str(env_path), override=True)
    return os.environ


def _block_to_dict(block: Any) -> dict[str, Any] | None:
    """Serialize one Anthropic SDK content block to a wire dict, preserving
    thinking (incl. signature), text, and tool_use verbatim."""
    btype = getattr(block, "type", None)
    if btype == "thinking":
        return {
            "type": "thinking",
            "thinking": getattr(block, "thinking", "") or "",
            "signature": getattr(block, "signature", "") or "",
        }
    if btype == "text":
        return {"type": "text", "text": getattr(block, "text", "") or ""}
    if btype == "tool_use":
        args = getattr(block, "input", None)
        if isinstance(args, str):
            import json

            try:
                args = json.loads(args)
            except Exception:
                args = {"_raw": args}
        return {
            "type": "tool_use",
            "id": getattr(block, "id", "") or "",
            "name": getattr(block, "name", "") or "",
            "input": dict(args or {}),
        }
    return None  # drop unknown block types


# Bound the per-run turn cache so a long run can't grow it without limit.
_TURN_CACHE_LIMIT = 256


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
        # tool_use_id -> full wire content blocks of the assistant turn that
        # produced that id (incl. thinking). Populated as responses arrive.
        self._turn_blocks: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()

    def _client(self):
        if self._client_override is not None:
            return self._client_override
        from anthropic import Anthropic

        return Anthropic()  # SDK reads ANTHROPIC_AUTH_TOKEN (Bearer) + ANTHROPIC_BASE_URL

    def count_tokens(self, *, system: str, messages: list[LLMMessage], model: str) -> int:
        """Token estimate: real gateway count_tokens with a chars/4 heuristic fallback.

        The MiniMax gateway supports `POST /anthropic/v1/messages/count_tokens`
        for M3, but it can reject some tool-loop message shapes (rebuilt
        assistant turns + tool_result), surfacing as llm.network_error in the
        runtime's pre-call cost gate. Try the real count first; fall back to a
        char/4 estimate on any failure so the cost gate always works.
        """
        try:
            return int(super().count_tokens(system=system, messages=messages, model=model))
        except Exception:
            total = len(system or "")
            for m in messages:
                total += len(getattr(m, "content", "") or "")
                for tc in getattr(m, "tool_calls", None) or ():
                    import json

                    total += len(tc.name) + len(
                        json.dumps(getattr(tc, "args", None) or {}, default=str)
                    )
            return max(1, total // 4)

    # ── thinking-preserving tool-loop turn cache ──────────────────────────
    def _remember_turn(self, raw: Any) -> None:
        ids = [tc.id for tc in _extract_tool_calls(raw) if tc.id]
        if not ids:
            return
        blocks = [
            b for b in (_block_to_dict(x) for x in (getattr(raw, "content", None) or [])) if b
        ]
        for tid in ids:
            self._turn_blocks[tid] = blocks
            self._turn_blocks.move_to_end(tid)
        while len(self._turn_blocks) > _TURN_CACHE_LIMIT:
            self._turn_blocks.popitem(last=False)

    def _restore_thinking(self, wire_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """For each echoed assistant tool-turn whose tool_use_id we remember,
        replace its rebuilt content with the cached full blocks (thinking included)."""
        for msg in wire_messages:
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            tool_ids = [
                b.get("id") for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
            ]
            cached = next(
                (self._turn_blocks.get(tid) for tid in tool_ids if tid in self._turn_blocks), None
            )
            if cached is not None:
                msg["content"] = list(cached)
        return wire_messages

    # ── complete(): mirrors AnthropicProvider.complete with thinking restore ─
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
        wire_messages = self._restore_thinking([_message_to_anthropic(m) for m in messages])
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
        # Enable interleaved thinking for M3 (off by default at the gateway).
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

        # Cache this turn's full blocks (thinking+text+tool_use) so the next
        # tool-loop iteration can echo them faithfully.
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
            provider_meta={"thinking_preserved": bool(self._turn_blocks)},
        )
