"""Router model integration tests for ModelRegistry + ModelSelector (M011 S03).

Registers real router models (minimax/MiniMax-M3, minimax/MiniMax-M2.7) as
ModelGenome instances and verifies per-stage routing. Gated real-router test
confirms both models respond through http://127.0.0.1:20128.
"""

from __future__ import annotations

import pytest

from active_skill_system.application.model_registry import ModelRegistry
from active_skill_system.application.model_selector import ModelSelector, StageType
from active_skill_system.domain.model_genome import ModelCapability, ModelGenome


def _router_registry() -> ModelRegistry:
    """Registry with real router models."""
    reg = ModelRegistry()
    reg.register(
        ModelGenome(
            id="minimax/MiniMax-M3",
            capabilities=frozenset({ModelCapability.VISION, ModelCapability.THINKING, ModelCapability.TOOLS}),
            context_window=1_000_000,
            cost_input_per_1m=1.0,
            cost_output_per_1m=2.0,
            provider_id="router",
        )
    )
    reg.register(
        ModelGenome(
            id="minimax/MiniMax-M2.7",
            capabilities=frozenset({ModelCapability.FAST, ModelCapability.STRUCTURED_OUTPUT}),
            context_window=200_000,
            cost_input_per_1m=0.1,
            cost_output_per_1m=0.2,
            provider_id="router",
        )
    )
    return reg


# ── Per-stage routing with real router models ─────────────────────────────


def test_router_vision_stage_selects_m3() -> None:
    reg = _router_registry()
    sel = ModelSelector()
    result = sel.select(
        StageType.VISION_EXTRACTION,
        frozenset({ModelCapability.VISION}),
        reg,
    )
    assert result is not None
    assert result.id == "minimax/MiniMax-M3"


def test_router_parse_stage_selects_m27() -> None:
    reg = _router_registry()
    sel = ModelSelector()
    result = sel.select(StageType.PARSE, frozenset(), reg)
    assert result is not None
    assert result.id == "minimax/MiniMax-M2.7"


def test_router_synthesize_stage_selects_m3() -> None:
    reg = _router_registry()
    sel = ModelSelector()
    result = sel.select(StageType.SYNTHESIZE, frozenset(), reg)
    assert result is not None
    assert result.id == "minimax/MiniMax-M3"


def test_router_repair_stage_selects_m3() -> None:
    reg = _router_registry()
    sel = ModelSelector()
    result = sel.select(
        StageType.REPAIR,
        frozenset({ModelCapability.TOOLS}),
        reg,
    )
    assert result is not None
    assert result.id == "minimax/MiniMax-M3"


# ── Gated real-router test ────────────────────────────────────────────────


@pytest.mark.llm
def test_real_router_both_models_respond() -> None:
    """Both M3 and M2.7 respond through the local router."""
    from pathlib import Path

    import anthropic
    from dotenv import load_dotenv

    load_dotenv(Path.cwd() / ".env", override=True)
    client = anthropic.Anthropic()

    for model_id in ("minimax/MiniMax-M3", "minimax/MiniMax-M2.7"):
        msg = client.messages.create(
            model=model_id,
            max_tokens=16,
            messages=[{"role": "user", "content": "Reply: pong"}],
        )
        assert msg.content is not None
        # Content can be thinking blocks or text blocks; M2.7 may return
        # only thinking blocks within max_tokens=16 — check we got *something*.
        assert len(msg.content) > 0
