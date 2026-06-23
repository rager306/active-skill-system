"""L2 outbound port — LLM provider (ModelGateway) abstraction.

The application depends on this Protocol; L3 adapters (e.g.
`active_skill_system.adapters.llm.minimax.MiniMaxProvider`) implement it.
Deliberately independent of activegraph/anthropic so the application layer
stays infra-free (enforced by import-linter).

Note: at runtime, ActiveGraph expects its own `LLMProvider` Protocol; the
MiniMax adapter satisfies both. This port is the application's declared
contract and the seam for swapping providers.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProviderPort(Protocol):
    """Minimal contract the application requires of an LLM provider."""

    default_model: str

    def complete(
        self,
        *,
        system: str,
        messages: list[Any],
        model: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        output_schema: Any | None,
        timeout_seconds: float,
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Return a response carrying raw_text + token/cost usage."""
        ...
