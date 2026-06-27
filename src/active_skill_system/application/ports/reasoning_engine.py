"""L2 Application — ReasoningEnginePort (M043, D016/D017).

Generic reasoning-strategy seam. All reasoning backends (PlainLLM, DSPy
CoT/ReAct/PoT/RLM, fast-rlm, future engines) implement this Protocol. The
application depends on this port, never on a concrete strategy or third-party
reasoning library (R002).

The port is intentionally narrow: ``forward(request) -> result``. Strategy
selection (which adapter to use) is a composition-time concern — the port makes
reasoning pluggable the same way ``LLMProviderPort`` makes LLM providers
pluggable.

D016/D017 strategy map (doc/dspy-research.md §7):
  - PlainLLMStrategy   (wraps LLMProviderPort.complete — current default)
  - DSPyStrategy        (dspy.ChainOfThought / ReAct / ProgramOfThought / RLM)
  - FastRLMStrategy     (fast-rlm: ACP delegation + structured-output routing)
  - (future engines)

Pure application. Depends on stdlib only (R002).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ReasoningRequest:
    """Input to a reasoning strategy.

    Carries:
      - system: system prompt for the reasoning model.
      - prompt: the user-facing task prompt.
      - model: model id (resolved by the strategy / provider).
      - max_tokens: generation budget (use the model's full window by default).
      - temperature: sampling temperature (0.0 = deterministic).
      - timeout_seconds: per-call timeout.
    """

    system: str
    prompt: str
    model: str
    max_tokens: int = 524_288
    temperature: float = 0.0
    timeout_seconds: float = 120.0


@dataclass(frozen=True)
class ReasoningResult:
    """Output of a reasoning strategy.

    Carries:
      - text: the generated text (e.g. code, answer).
      - model: the model that actually served the request.
      - finish_reason: why generation stopped ('end_turn', 'max_tokens', ...).
      - error: None on success; an error message on failure (strategy catches
        provider exceptions and degrades gracefully).
    """

    text: str
    model: str
    finish_reason: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        """True when the strategy produced a result without error."""
        return self.error is None and bool(self.text)


@runtime_checkable
class ReasoningEnginePort(Protocol):
    """Generic reasoning-strategy contract (D016/D017).

    Implementations (PlainLLMStrategy, DSPyStrategy, FastRLMStrategy) live in
    L3 adapters and are wired at composition time. The application depends on
    this Protocol, never on a concrete strategy.
    """

    def forward(self, request: ReasoningRequest) -> ReasoningResult:
        """Execute a reasoning request and return the result.

        Implementations MUST catch provider/engine exceptions and return a
        ReasoningResult with ``error`` set — never raise to the caller. This
        keeps the Loop (D009) degradation graceful.
        """
        ...
