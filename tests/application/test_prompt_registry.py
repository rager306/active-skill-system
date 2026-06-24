"""Unit tests for PromptRegistry + PromptRenderer (M012 S02)."""

from __future__ import annotations

import pytest

from active_skill_system.application.prompt_registry import (
    PromptRegistry,
    PromptRenderer,
)
from active_skill_system.domain.prompt_genome import PromptGenome, PromptSlot


def _genome(
    id: str = "test",
    template: str = "Hello {name}",
    slots: tuple[PromptSlot, ...] = (PromptSlot("name"),),
    version: int = 1,
) -> PromptGenome:
    return PromptGenome(id=id, template=template, slots=slots, version=version)


# ── PromptRegistry ────────────────────────────────────────────────────────


def test_registry_register_and_get_latest() -> None:
    reg = PromptRegistry()
    reg.register(_genome(version=1))
    reg.register(_genome(version=2, template="Hi {name}"))
    g = reg.get_by_id("test")
    assert g is not None
    assert g.version == 2
    assert "Hi" in g.template


def test_registry_get_specific_version() -> None:
    reg = PromptRegistry()
    reg.register(_genome(version=1, template="v1"))
    reg.register(_genome(version=2, template="v2"))
    g = reg.get_by_id("test", version=1)
    assert g is not None
    assert g.template == "v1"


def test_registry_get_nonexistent_returns_none() -> None:
    reg = PromptRegistry()
    assert reg.get_by_id("nope") is None


def test_registry_list_all() -> None:
    reg = PromptRegistry()
    reg.register(_genome(id="a", version=1))
    reg.register(_genome(id="b", version=1))
    assert len(reg.list_all()) == 2


def test_registry_reregister_same_version_replaces() -> None:
    reg = PromptRegistry()
    reg.register(_genome(version=1, template="old"))
    reg.register(_genome(version=1, template="new"))
    assert len(reg.list_all()) == 1
    assert reg.get_by_id("test").template == "new"


# ── PromptRenderer ────────────────────────────────────────────────────────


def test_renderer_fills_all_slots() -> None:
    g = _genome(
        template="Hello {name}, you are {role}",
        slots=(PromptSlot("name"), PromptSlot("role")),
    )
    rendered = PromptRenderer().render(g, {"name": "Alice", "role": "admin"})
    assert "Alice" in rendered
    assert "admin" in rendered


def test_renderer_missing_required_slot_raises() -> None:
    g = _genome(slots=(PromptSlot("name"),))
    with pytest.raises(ValueError, match="required slot"):
        PromptRenderer().render(g, {})


def test_renderer_optional_slot_uses_default() -> None:
    g = _genome(
        slots=(PromptSlot("name"), PromptSlot("greeting", required=False, default="Hi")),
        template="{greeting} {name}",
    )
    rendered = PromptRenderer().render(g, {"name": "Bob"})
    assert "Hi" in rendered


def test_renderer_optional_slot_without_default_is_empty() -> None:
    g = _genome(
        slots=(PromptSlot("name"), PromptSlot("extra", required=False)),
        template="{name}-{extra}",
    )
    rendered = PromptRenderer().render(g, {"name": "X"})
    assert rendered == "X-"
