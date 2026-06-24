"""Unit tests for PromptGenome + PromptSlot (M012 S01)."""

from __future__ import annotations

import pytest

from active_skill_system.domain.prompt_genome import PromptGenome, PromptSlot


def _valid_genome(**overrides) -> PromptGenome:
    defaults = dict(
        id="parse_task_spec",
        template="Extract JSON from {goal}",
        slots=(PromptSlot(name="goal"),),
    )
    defaults.update(overrides)
    return PromptGenome(**defaults)


def test_prompt_genome_constructs() -> None:
    g = _valid_genome()
    assert g.id == "parse_task_spec"
    assert "{goal}" in g.template
    assert g.version == 1


def test_slot_names() -> None:
    g = _valid_genome(slots=(PromptSlot("a"), PromptSlot("b", required=False)))
    assert g.slot_names() == ("a", "b")


def test_rejects_empty_id() -> None:
    with pytest.raises(ValueError, match="id"):
        _valid_genome(id="")


def test_rejects_empty_template() -> None:
    with pytest.raises(ValueError, match="template"):
        _valid_genome(template="")


def test_rejects_empty_slots() -> None:
    with pytest.raises(ValueError, match="slots"):
        _valid_genome(slots=())


def test_rejects_zero_version() -> None:
    with pytest.raises(ValueError, match="version"):
        _valid_genome(version=0)


def test_prompt_slot_optional_default() -> None:
    s = PromptSlot(name="x", required=False, default="fallback")
    assert s.required is False
    assert s.default == "fallback"


def test_prompt_slot_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="name"):
        PromptSlot(name="")


def test_frozen_hashable() -> None:
    g = _valid_genome()
    assert hash(g) == hash(g)


def test_module_infra_free() -> None:
    import importlib
    from pathlib import Path

    mod = importlib.import_module("active_skill_system.domain.prompt_genome")
    src = Path(mod.__file__).read_text()
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"prompt_genome.py must not contain '{forbidden}' (R002)"
