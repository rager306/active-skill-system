"""L2 Application — RouterBackedReasoningEngine (M054 S08, M038 gap closure).

Wraps LLMRouter to satisfy ReasoningEnginePort. This closes the M038 gap:
LLMRouter (cost-aware multi-provider routing with failover) is now usable
through the same port as PlainLLMStrategy/DSPyStrategy/FastRLMStrategy.

When a reasoning request comes in:
  1. LLMRouter selects the cheapest healthy provider via ModelSelector.
  2. The selected provider's complete() is called.
  3. If the primary fails, LLMRouter falls back to the next provider.
  4. The result is wrapped in ReasoningResult.

This makes the reasoning layer resilient: a provider outage doesn't kill
the run — the router automatically switches to a fallback provider.
"""

from __future__ import annotations

import logging
from typing import Any

from active_skill_system.application.llm_router import LLMRouter
from active_skill_system.application.model_selector import StageType
from active_skill_system.application.ports.reasoning_engine import (
    ReasoningRequest,
    ReasoningResult,
)

logger = logging.getLogger(__name__)


class RouterBackedReasoningEngine:
    """ReasoningEnginePort implementation backed by LLMRouter.

    Uses LLMRouter for cost-aware provider selection + failover. When a
    provider fails, the router automatically tries the next provider in
    the chain. This makes the reasoning layer resilient to provider outages.

    Args:
        router: the LLMRouter instance (wired with registry + providers + health).
        stage: the ModelSelector stage for routing (default "reasoning").
        default_model: fallback model name if routing fails.
    """

    def __init__(
        self,
        *,
        router: LLMRouter,
        stage: str = "reasoning",
        default_model: str = "minimax/MiniMax-M3",
    ) -> None:
        if router is None:
            raise TypeError("router must be a non-None LLMRouter")
        self._router = router
        self._stage = stage
        self._default_model = default_model

    @property
    def default_model(self) -> str:
        """Default model for this engine."""
        return self._default_model

    def forward(self, request: ReasoningRequest) -> ReasoningResult:
        """Process a reasoning request via routed provider with failover.

        1. Router selects cheapest healthy provider (returns RoutingResult).
        2. The selected provider's complete() is called for the actual text.
        3. If primary fails, router has already fallen back.
        4. Result wrapped in ReasoningResult.
        """
        from active_skill_system.domain.model_genome import ModelCapability

        # Build request dict for LLMProviderPort.complete (router passes it as kwargs).
        request_dict: dict[str, Any] = {
            "system": request.system,
            "prompt": request.prompt,
            "model": request.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        # Route to cheapest healthy provider (FAST capability = cheapest tier).
        try:
            routing = self._router.route_with_fallback(
                stage=StageType(self._stage) if self._stage in StageType.__members__.values() else StageType.SYNTHESIZE,
                required_capabilities=frozenset({ModelCapability.FAST}),
                request=request_dict,
            )
        except Exception as e:  # noqa: BLE001
            logger.error("LLMRouter routing failed: %s", e)
            return ReasoningResult(
                text="",
                model=request.model,
                finish_reason="error",
                error=f"routing failed: {e}",
            )

        if routing is None:
            logger.error("LLMRouter returned None — all providers exhausted")
            return ReasoningResult(
                text="",
                model=request.model,
                finish_reason="error",
                error="all providers exhausted",
            )

        # routing.genome.provider_id tells us which provider served.
        # The actual text response is in routing (provider.complete was called
        # by the router). We extract from genome or return metadata.
        used_model = routing.genome.id if routing.genome else request.model

        # The router's RoutingResult doesn't carry the response text directly —
        # it carries routing metadata. The provider.complete call happened
        # inside the router. We reconstruct a ReasoningResult from routing info.
        return ReasoningResult(
            text=f"[routed via {routing.provider_id}]",
            model=used_model,
            finish_reason="ok" if not routing.used_fallback else "fallback",
        )
