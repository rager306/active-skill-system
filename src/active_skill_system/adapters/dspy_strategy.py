"""L3 Adapter — DSPyStrategy (M051 S01, D015/D016/D017).

Implements ReasoningEnginePort via DSPy's ChainOfThought module. When DSPy
is not installed or the LLM call fails, falls back to a documented stub
mode that returns a structured ReasoningResult with finish_reason="stub"
and an explanatory error message — no silent fallback.

D015 stance: DSPy is a reasoning substrate behind our port, not a
replacement for PlainLLMStrategy. Both strategies live in L3; composition
chooses via --strategy {plain,dspy}.

Layering (R002): this adapter is L3 (activegraph/dspy infra), composition
imports it. No domain or application imports here.
"""

from __future__ import annotations

import logging
from typing import Any

from active_skill_system.application.ports.reasoning_engine import (
    ReasoningRequest,
    ReasoningResult,
)

_log = logging.getLogger(__name__)


class DSPyStrategy:
    """Reasoning strategy backed by DSPy.ChainOfThought.

    Lazy-imports DSPy. Falls back to stub mode (with finish_reason="stub")
    if DSPy is not installed, LM setup fails, or the call errors. Never
    raises — graceful Loop degradation (D009).

    Args:
        model: DSPy model identifier (e.g. "minimax/MiniMax-M3").
        api_base: Anthropic-compatible base URL (e.g. proxy).
        api_key: API key for the LM.
        max_tokens: per-call budget.
        temperature: sampling temperature.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        max_tokens: int = 524_288,
        temperature: float = 0.0,
    ) -> None:
        self._model = model
        self._api_base = api_base
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._dspy_lm: Any = None
        self._stub_reason: str | None = None
        self._setup_lm()

    def _setup_lm(self) -> None:
        """Try to import DSPy and configure a dspy.LM.

        On any failure (ImportError, missing env var, network error), set
        _stub_reason and stay in stub mode. We never raise.
        """
        try:
            import os

            import dspy  # noqa: PLC0415 — lazy import per M051 design

            api_base = self._api_base or os.environ.get("ANTHROPIC_BASE_URL")
            api_key = self._api_key or os.environ.get("ANTHROPIC_AUTH_TOKEN")
            model = self._model or os.environ.get("ANTHROPIC_MODEL", "minimax/MiniMax-M3")

            if not api_base or not api_key:
                self._stub_reason = "DSPy LM not configured (missing ANTHROPIC_BASE_URL or ANTHROPIC_AUTH_TOKEN)"
                _log.warning("dspy_strategy_stubbed reason=%s", self._stub_reason)
                return

            # DSPy 3.x via LiteLLM requires explicit provider prefix on the
            # model name (e.g. "anthropic/..."). The plain model name
            # "MiniMax-M3" works for AnthropicProvider direct calls but not
            # for LiteLLM-routed DSPy. We add the prefix when it is missing.
            if "/" not in model:
                model = f"anthropic/{model}"

            # DSPy 3.x LM signature: dspy.LM(model, api_base=..., api_key=..., max_tokens=...)
            self._dspy_lm = dspy.LM(
                model=model,
                api_base=api_base,
                api_key=api_key,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
            dspy.configure(lm=self._dspy_lm)
            self._stub_reason = None
            _log.info("dspy_strategy_configured model=%s api_base=%s", model, api_base)
        except Exception as e:  # noqa: BLE001 — graceful stub fallback
            self._stub_reason = f"{type(e).__name__}: {e}"
            _log.warning("dspy_strategy_stubbed reason=%s", self._stub_reason)

    @property
    def is_stub(self) -> bool:
        """True when DSPy is unavailable and the strategy is degraded."""
        return self._stub_reason is not None

    @property
    def stub_reason(self) -> str | None:
        return self._stub_reason

    def forward(self, request: ReasoningRequest) -> ReasoningResult:
        """Run ChainOfThought over the request.

        Returns ReasoningResult(error=...) on any failure — never raises.
        """
        if self.is_stub:
            return ReasoningResult(
                text="",
                model=request.model,
                finish_reason="stub",
                error=f"dspy stub: {self._stub_reason}",
            )
        try:
            import dspy  # noqa: PLC0415

            # DSPy signature: input -> output text. We use a simple Signature.
            class GenerateSignature(dspy.Signature):  # type: ignore[misc]
                """Generate the requested text."""

                prompt = dspy.InputField()
                output = dspy.OutputField()

            predictor = dspy.ChainOfThought(GenerateSignature)
            result = predictor(prompt=request.prompt)
            text = getattr(result, "output", "") or str(result)
            return ReasoningResult(
                text=text,
                model=request.model,
                finish_reason="end_turn",
            )
        except Exception as e:  # noqa: BLE001 — graceful: never raise to caller
            return ReasoningResult(
                text="",
                model=request.model,
                finish_reason="stub",
                error=f"dspy call failed: {type(e).__name__}: {e}",
            )


# DSPyStrategy structurally satisfies ReasoningEnginePort (forward signature).
