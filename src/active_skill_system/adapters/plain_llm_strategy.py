"""L3 Adapter — PlainLLMStrategy (M043 S01 T02, D016/D017).

The default reasoning strategy: wraps an injected ``LLMProviderPort`` and
implements ``ReasoningEnginePort``. This is the zero-dependency baseline — no
DSPy, no fast-rlm, just a direct LLM call through the existing provider port.

Future strategies (DSPyStrategy, FastRLMStrategy) implement the same port and
are wired at composition time. PlainLLMStrategy catches provider exceptions and
returns ``ReasoningResult(error=...)`` — never raises to the caller (graceful
Loop degradation, D009).
"""

from __future__ import annotations

from active_skill_system.application.ports.llm import LLMMessage, LLMProviderPort
from active_skill_system.application.ports.reasoning_engine import (
    ReasoningRequest,
    ReasoningResult,
)


class PlainLLMStrategy:
    """Default reasoning strategy: direct LLMProviderPort.complete wrapper.

    Implements ReasoningEnginePort. The provider is injected (REQUIRED, R002).
    """

    def __init__(self, *, provider: LLMProviderPort, cache: Any = None) -> None:
        if provider is None:
            raise TypeError("provider must be a non-None LLMProviderPort")
        if not hasattr(provider, "complete") or not hasattr(provider, "default_model"):
            raise TypeError("provider must satisfy LLMProviderPort (complete + default_model)")
        self._provider = provider
        self._cache = cache

    def forward(self, request: ReasoningRequest) -> ReasoningResult:
        """Call the LLM provider and map the response to ReasoningResult.

        If a cache is configured, checks cache before calling the provider.
        On cache hit, returns the cached response without an LLM call.
        """
        if self._cache is not None:
            from active_skill_system.application.ports.llm_cache import cache_key

            key = cache_key(
                model=request.model, system=request.system, prompt=request.prompt,
                max_tokens=request.max_tokens, temperature=request.temperature,
            )
            cached = self._cache.get(key)
            if cached is not None:
                return ReasoningResult(
                    text=cached.get("text", ""),
                    model=cached.get("model", request.model),
                    finish_reason=cached.get("finish_reason", "cached"),
                )
        try:
            response = self._provider.complete(
                system=request.system,
                messages=[LLMMessage(role="user", content=request.prompt)],
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=1.0,
                output_schema=None,
                timeout_seconds=request.timeout_seconds,
            )
        except Exception as e:  # noqa: BLE001 — graceful: never raise to caller
            return ReasoningResult(
                text="",
                model=request.model,
                error=f"{type(e).__name__}: {e}",
            )
        result = ReasoningResult(
            text=getattr(response, "raw_text", "") or str(response),
            model=getattr(response, "model", request.model),
            finish_reason=getattr(response, "finish_reason", ""),
        )
        # Record in cache (M052 S05).
        if self._cache is not None:
            from active_skill_system.application.ports.llm_cache import cache_key

            key = cache_key(
                model=request.model, system=request.system, prompt=request.prompt,
                max_tokens=request.max_tokens, temperature=request.temperature,
            )
            self._cache.record(key, {
                "text": result.text,
                "model": result.model,
                "finish_reason": result.finish_reason,
            })
        return result


# PlainLLMStrategy structurally satisfies ReasoningEnginePort.
# (Runtime check omitted — constructing with None provider raises by design.)
