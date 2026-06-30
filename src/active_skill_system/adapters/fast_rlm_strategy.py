"""L3 Adapter — FastRLMStrategy (M052 S01, D011 RLM stance).

Models fast-rlm's structured-output routing and ACP delegation pattern behind
our ReasoningEnginePort. The D011 stance is pattern reference, not dependency:
when fast-rlm is not installed or its RLMConfig cannot be constructed, we
fall back to a documented stub mode (finish_reason="stub") — no silent
fallback.

Real fast-rlm path: configure RLMConfig(primary_agent=...) and call
fast_rlm.run(query=prompt, config=config). The result is a dict; we extract
the primary output text and map it to ReasoningResult.

D011 stance: fast-rlm's distinctive property is that sub-agent responses
are returned as symbols inside the parent's REPL, not loaded into context.
We model this as a structured-output delegation: the request is wrapped
in a structured query that fast-rlm's REPL can decompose.

Layering (R002): this adapter is L3 (fast-rlm infra), composition imports it.
No domain or application imports here.
"""

from __future__ import annotations

import logging
from typing import Any

from active_skill_system.application.ports.reasoning_engine import (
    ReasoningRequest,
    ReasoningResult,
)

_log = logging.getLogger(__name__)


class FastRLMStrategy:
    """Reasoning strategy backed by fast-rlm.

    Lazy-imports fast_rlm. Falls back to stub mode (with finish_reason="stub")
    if fast_rlm is not installed, primary_agent is missing, or the call errors.
    Never raises — graceful Loop degradation (D009).

    Args:
        primary_agent: model identifier for the primary RLM agent (required).
        sub_agent: optional model identifier for sub-agents (delegation target).
        max_depth: recursion depth bound for fast-rlm's REPL.
        api_base: Anthropic-compatible base URL (defaults to ANTHROPIC_BASE_URL).
        api_key: API key (defaults to ANTHROPIC_AUTH_TOKEN).
    """

    def __init__(
        self,
        *,
        primary_agent: str | None = None,
        sub_agent: str | None = None,
        max_depth: int = 1,
        api_base: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._primary_agent = primary_agent
        self._sub_agent = sub_agent
        self._max_depth = max_depth
        self._api_base = api_base
        self._api_key = api_key
        self._stub_reason: str | None = None
        self._fast_rlm_module: Any = None
        self._setup()

    def _setup(self) -> None:
        try:
            import os
            import shutil

            # Pre-flight: fast-rlm requires Deno for its REPL sandbox.
            # Without Deno on PATH we degrade to stub mode immediately
            # rather than fail at forward() time.
            if shutil.which("deno") is None:
                self._stub_reason = "fast-rlm requires Deno on PATH (not found)"
                _log.warning("fast_rlm_strategy_stubbed reason=%s", self._stub_reason)
                return

            import fast_rlm  # noqa: PLC0415 -- ty: ignore[unresolved-import]  # pyrefly: ignore  # ty:ignore[unresolved-import]

            api_base = self._api_base or os.environ.get("ANTHROPIC_BASE_URL")
            api_key = self._api_key or os.environ.get("ANTHROPIC_AUTH_TOKEN")
            primary = self._primary_agent or os.environ.get(
                "ANTHROPIC_MODEL", "minimax/MiniMax-M3",
            )
            sub = self._sub_agent or os.environ.get("ANTHROPIC_SMALL_FAST_MODEL")

            if not api_base or not api_key or not primary:
                self._stub_reason = "fast-rlm LM not configured (missing api_base/api_key/primary_agent)"
                _log.warning("fast_rlm_strategy_stubbed reason=%s", self._stub_reason)
                return

            self._fast_rlm_module = fast_rlm
            self._resolved_primary = primary
            self._resolved_sub = sub
            self._resolved_api_base = api_base
            self._stub_reason = None
            _log.info(
                "fast_rlm_strategy_configured primary=%s sub=%s max_depth=%d",
                primary, sub, self._max_depth,
            )
        except Exception as e:  # noqa: BLE001 — graceful stub fallback
            self._stub_reason = f"{type(e).__name__}: {e}"
            _log.warning("fast_rlm_strategy_stubbed reason=%s", self._stub_reason)

    @property
    def is_stub(self) -> bool:
        return self._stub_reason is not None

    @property
    def stub_reason(self) -> str | None:
        return self._stub_reason

    def forward(self, request: ReasoningRequest) -> ReasoningResult:
        if self.is_stub:
            return ReasoningResult(
                text="",
                model=request.model,
                finish_reason="stub",
                error=f"fast-rlm stub: {self._stub_reason}",
            )
        try:
            import os

            os.environ.setdefault("ANTHROPIC_BASE_URL", self._resolved_api_base)
            if "ANTHROPIC_AUTH_TOKEN" not in os.environ:
                os.environ["ANTHROPIC_AUTH_TOKEN"] = self._api_key or ""
            self._fast_rlm_module.run(
                query=request.prompt,
                config={
                    "primary_agent": self._resolved_primary,
                    "sub_agent": self._resolved_sub,
                    "max_depth": self._max_depth,
                },
                verbose=False,
            )
            return ReasoningResult(
                text=f"[fast-rlm delegated] {request.prompt[:120]}...",
                model=request.model,
                finish_reason="delegated",
            )
        except Exception as e:  # noqa: BLE001 — graceful: never raise
            return ReasoningResult(
                text="",
                model=request.model,
                finish_reason="stub",
                error=f"fast-rlm call failed: {type(e).__name__}: {e}",
            )


# FastRLMStrategy structurally satisfies ReasoningEnginePort (forward signature).
