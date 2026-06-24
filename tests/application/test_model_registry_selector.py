"""Unit tests for ModelRegistry + ModelSelector (M011 S02)."""

from __future__ import annotations

from active_skill_system.application.model_registry import ModelRegistry
from active_skill_system.application.model_selector import ModelSelector, StageType
from active_skill_system.domain.model_genome import ModelCapability, ModelGenome


def _m3() -> ModelGenome:
    return ModelGenome(
        id="minimax-m3",
        capabilities=frozenset({ModelCapability.VISION, ModelCapability.THINKING}),
        context_window=1_000_000,
        cost_input_per_1m=1.0,
        cost_output_per_1m=2.0,
        provider_id="router",
    )


def _m27() -> ModelGenome:
    return ModelGenome(
        id="minimax-m2.7",
        capabilities=frozenset({ModelCapability.FAST, ModelCapability.STRUCTURED_OUTPUT}),
        context_window=200_000,
        cost_input_per_1m=0.1,
        cost_output_per_1m=0.2,
        provider_id="router",
    )


# ── ModelRegistry ─────────────────────────────────────────────────────────


def test_registry_register_and_get_by_id() -> None:
    reg = ModelRegistry()
    reg.register(_m3())
    assert reg.get_by_id("minimax-m3") is not None
    assert reg.get_by_id("nonexistent") is None


def test_registry_list_by_capability() -> None:
    reg = ModelRegistry()
    reg.register(_m3())
    reg.register(_m27())
    vision = reg.list_by_capability(ModelCapability.VISION)
    assert len(vision) == 1
    assert vision[0].id == "minimax-m3"
    fast = reg.list_by_capability(ModelCapability.FAST)
    assert len(fast) == 1
    assert fast[0].id == "minimax-m2.7"


def test_registry_list_all() -> None:
    reg = ModelRegistry()
    reg.register(_m3())
    reg.register(_m27())
    assert len(reg.list_all()) == 2


def test_registry_reregister_replaces() -> None:
    reg = ModelRegistry()
    reg.register(_m3())
    reg.register(_m3())  # same id
    assert len(reg.list_all()) == 1


# ── ModelSelector ─────────────────────────────────────────────────────────


def _registry_with_both() -> ModelRegistry:
    reg = ModelRegistry()
    reg.register(_m3())
    reg.register(_m27())
    return reg


def test_selector_vision_stage_picks_m3() -> None:
    """Vision extraction requires VISION capability → only M3 qualifies."""
    sel = ModelSelector()
    result = sel.select(
        StageType.VISION_EXTRACTION,
        frozenset({ModelCapability.VISION}),
        _registry_with_both(),
    )
    assert result is not None
    assert result.id == "minimax-m3"


def test_selector_parse_stage_picks_fast_model() -> None:
    """Parse stage prefers FAST → M2.7 is cheaper and faster."""
    sel = ModelSelector()
    result = sel.select(StageType.PARSE, frozenset(), _registry_with_both())
    assert result is not None
    assert result.id == "minimax-m2.7"


def test_selector_synthesize_prefers_thinking() -> None:
    """Synthesize stage prefers THINKING → M3 has it, M2.7 doesn't."""
    sel = ModelSelector()
    result = sel.select(StageType.SYNTHESIZE, frozenset(), _registry_with_both())
    assert result is not None
    assert result.id == "minimax-m3"


def test_selector_returns_none_when_no_match() -> None:
    """No model with required TOOLS capability → None."""
    sel = ModelSelector()
    result = sel.select(
        StageType.REPAIR,
        frozenset({ModelCapability.TOOLS}),
        _registry_with_both(),
    )
    assert result is None


def test_selector_default_picks_cheapest() -> None:
    """Default stage (no preference) → cheapest model."""
    sel = ModelSelector()
    result = sel.select(StageType.DEFAULT, frozenset(), _registry_with_both())
    assert result is not None
    assert result.id == "minimax-m2.7"


def test_selector_empty_registry_returns_none() -> None:
    sel = ModelSelector()
    result = sel.select(StageType.DEFAULT, frozenset(), ModelRegistry())
    assert result is None
