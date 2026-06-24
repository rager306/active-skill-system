"""Thinking-preservation turn cache for the MiniMax adapter.

activegraph rebuilds a tool-loop assistant turn from ``raw_text + tool_calls``
and DROPS the ``thinking`` blocks. MiniMax-M3 uses interleaved thinking and
the Anthropic spec requires the full content list (incl. thinking with its
signature) to be echoed back, or the gateway rejects the tool result with
error 2013 "tool result's tool id not found".

This module is a pure data structure (stdlib + typing only): it remembers the
full wire content blocks of an assistant turn keyed by ``tool_use_id`` and, on
the next turn, replaces the rebuilt assistant turn with the cached full blocks
(thinking included). The provider wires it to activegraph response objects.

Exported:
    _block_to_dict  — serialize one Anthropic SDK content block to a wire dict.
    ThinkingTurnCache — bounded tool_use_id -> full-blocks cache.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any

# Bound the per-run turn cache so a long run can't grow it without limit.
_TURN_CACHE_LIMIT = 256


def _block_to_dict(block: Any) -> dict[str, Any] | None:
    """Serialize one Anthropic SDK content block to a wire dict, preserving
    thinking (incl. signature), text, and tool_use verbatim.

    Returns ``None`` for unknown block types (dropped).
    Duck-typed (``getattr``): no activegraph import required.
    """
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
            try:
                args = json.loads(args)
            except Exception:  # noqa: BLE001 - keep best-effort dict
                args = {"_raw": args}
        return {
            "type": "tool_use",
            "id": getattr(block, "id", "") or "",
            "name": getattr(block, "name", "") or "",
            "input": dict(args or {}),
        }
    return None  # drop unknown block types


class ThinkingTurnCache:
    """Bounded ``tool_use_id -> full wire content blocks`` cache.

    ``remember`` stores the full blocks (incl. thinking) of an assistant turn
    under each of its tool-use ids. ``restore`` swaps any rebuilt assistant
    turn whose tool-use id we remember back to the cached full blocks.
    """

    def __init__(self, limit: int = _TURN_CACHE_LIMIT) -> None:
        self._limit = limit
        self.blocks: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()

    def remember(self, tool_use_ids: list[str], full_blocks: list[dict[str, Any]]) -> None:
        """Cache ``full_blocks`` under each id in ``tool_use_ids``.

        Empty ``tool_use_ids`` is a no-op (a turn with no tool calls is not
        worth caching — there is nothing to restore on the next turn).
        """
        if not tool_use_ids:
            return
        for tid in tool_use_ids:
            self.blocks[tid] = list(full_blocks)
            self.blocks.move_to_end(tid)
        while len(self.blocks) > self._limit:
            self.blocks.popitem(last=False)

    def restore(self, wire_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """For each echoed assistant tool-turn whose tool_use_id we remember,
        replace its rebuilt content with the cached full blocks (thinking included).

        Non-assistant turns and tool_result messages are left untouched.
        """
        for msg in wire_messages:
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            tool_ids = [
                b.get("id")
                for b in content
                if isinstance(b, dict) and b.get("type") == "tool_use"
            ]
            cached = next(
                (self.blocks.get(tid) for tid in tool_ids if tid in self.blocks), None
            )
            if cached is not None:
                msg["content"] = list(cached)
        return wire_messages
