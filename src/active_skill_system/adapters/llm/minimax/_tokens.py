"""Token-count fallback heuristic for the MiniMax adapter.

The MiniMax gateway exposes ``POST /anthropic/v1/messages/count_tokens`` for
M3, but it can reject some tool-loop message shapes (rebuilt assistant turns +
tool_result), surfacing as ``llm.network_error`` in the runtime's pre-call
cost gate. ``MiniMaxProvider.count_tokens`` tries the real gateway count first
and falls back to this char/4 estimate on any failure so the cost gate always
works.

Pure function, no I/O.
"""

from __future__ import annotations

import json
from typing import Any


def count_tokens_fallback(
    *, system: str, messages: list[Any], model: str  # noqa: ARG001 - model unused in heuristic
) -> int:
    """Char/4 token estimate over system text + message content + tool calls.

    Args:
        system: system prompt text (may be empty).
        messages: list of message objects with ``content`` (str) and optional
            ``tool_calls`` (sequence of objects with ``name``/``args``).
        model: model id (unused by the heuristic, kept for signature parity).

    Returns:
        At least 1 — a zero/negative estimate would break the cost gate.
    """
    total = len(system or "")
    for m in messages:
        total += len(getattr(m, "content", "") or "")
        for tc in getattr(m, "tool_calls", None) or ():
            total += len(tc.name)
            total += len(json.dumps(getattr(tc, "args", None) or {}, default=str))
    return max(1, total // 4)
