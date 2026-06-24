"""Unit tests for ModelGenome + ModelCapability (M011 S01)."""

from __future__ import annotations

import pytest

from active_skill_system.domain.model_genome import ModelCapability, ModelGenome


def _valid_genome(**overrides) -> ModelGenome:
    defaults = dict(
        id="minimax-m3",
        capabilities=frozenset({ModelCapability.VISION, ModelCapability.THINKING}),
        context_window=1_000_000,
        cost_input_per_1m=1.0,
        cost_output_per_1m=2.0,
        provider_id="router",
    )
    defaults.update(overrides)
    return ModelGenome(**defaults)


def test_model_genome_constructs() -> None:
    m = _valid_genome()
    assert m.id == "minimax-m3"
    assert ModelCapability.VISION in m.capabilities
    assert m.context_window == 1_000_000


def test_has_capability() -> None:
    m = _valid_genome()
    assert m.has_capability(ModelCapability.VISION)
    assert not m.has_capability(ModelCapability.FAST)


def test_rejects_empty_id() -> None:
    with pytest.raises(ValueError, match="id"):
        _valid_genome(id="")


def test_rejects_empty_capabilities() -> None:
    with pytest.raises(ValueError, match="capabilities"):
        _valid_genome(capabilities=frozenset())


def test_rejects_zero_context_window() -> None:
    with pytest.raises(ValueError, match="context_window must be positive"):
        _valid_genome(context_window=0)


def test_rejects_negative_context_window() -> None:
    with pytest.raises(ValueError, match="context_window must be positive"):
        _valid_genome(context_window=-1)


def test_rejects_negative_cost() -> None:
    with pytest.raises(ValueError, match="cost_input_per_1m"):
        _valid_genome(cost_input_per_1m=-0.5)
    with pytest.raises(ValueError, match="cost_output_per_1m"):
        _valid_genome(cost_output_per_1m=-1.0)


def test_rejects_empty_provider_id() -> None:
    with pytest.raises(ValueError, match="provider_id"):
        _valid_genome(provider_id="")


def test_all_capabilities_present() -> None:
    expected = {"vision", "thinking", "tools", "structured_output", "streaming", "fast"}
    assert {c.value for c in ModelCapability} == expected


def test_frozen_hashable() -> None:
    m = _valid_genome()
    assert hash(m) == hash(m)


def test_module_infra_free() -> None:
    import importlib
    from pathlib import Path

    mod = importlib.import_module("active_skill_system.domain.model_genome")
    src = Path(mod.__file__).read_text()
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"model_genome.py must not contain '{forbidden}' (R002)"
