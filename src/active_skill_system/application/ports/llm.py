"""L2 outbound port — LLM provider (ModelGateway) abstraction.

The application depends on this Protocol; L3 adapters (e.g.
``active_skill_system.adapters.llm.minimax.MiniMaxProvider``) implement it.
Deliberately independent of activegraph/anthropic so the application layer
stays infra-free (enforced by import-linter).

The port uses local value types (``LLMMessage``, ``LLMToolCall``) defined
here, NOT ``activegraph.llm.types.LLMMessage``. The adapter converts at the
infra boundary. This keeps the application layer's import surface flat
(R002) and the contract explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

# ── local value types (infra-free) ────────────────────────────────────────

Role = Literal["user", "assistant", "system", "tool"]


@dataclass(frozen=True)
class LLMToolCall:
    """One tool invocation the model wants to make (local type)."""

    id: str
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMMessage:
    """A single chat message exchanged with the LLM (local, infra-free).

    Mirrors the fields the application actually needs; the adapter maps this
    onto the underlying SDK's native message type.
    """

    role: Role
    content: str = ""
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_calls: tuple[LLMToolCall, ...] = ()


# ── the port ───────────────────────────────────────────────────────────────


@runtime_checkable
class LLMProviderPort(Protocol):
    """Minimal contract the application requires of an LLM provider."""

    default_model: str

    def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
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
