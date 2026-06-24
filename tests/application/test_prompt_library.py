"""Unit tests for default prompt library (M012 S03)."""

from __future__ import annotations

from active_skill_system.application.prompt_library import default_prompt_registry
from active_skill_system.application.prompt_registry import PromptRenderer


def test_registry_contains_three_prompts() -> None:
    reg = default_prompt_registry()
    assert reg.get_by_id("parse_task_spec") is not None
    assert reg.get_by_id("vision_extraction") is not None
    assert reg.get_by_id("synthesize_answer") is not None


def test_parse_prompt_renders_with_goal() -> None:
    reg = default_prompt_registry()
    g = reg.get_by_id("parse_task_spec")
    assert g is not None
    rendered = PromptRenderer().render(g, {"goal": "summarise X"})
    assert "summarise X" in rendered
    assert "JSON" in rendered


def test_vision_prompt_renders_with_goal() -> None:
    reg = default_prompt_registry()
    g = reg.get_by_id("vision_extraction")
    assert g is not None
    rendered = PromptRenderer().render(g, {"goal": "describe image"})
    assert "describe image" in rendered


def test_synthesize_prompt_renders_with_all_slots() -> None:
    reg = default_prompt_registry()
    g = reg.get_by_id("synthesize_answer")
    assert g is not None
    rendered = PromptRenderer().render(
        g, {"goal": "answer Q", "facts": "- fact1", "claims": "- claim1"}
    )
    assert "answer Q" in rendered
    assert "fact1" in rendered
    assert "claim1" in rendered


def test_all_prompts_version_1() -> None:
    reg = default_prompt_registry()
    for gid in ("parse_task_spec", "vision_extraction", "synthesize_answer"):
        g = reg.get_by_id(gid)
        assert g is not None
        assert g.version == 1


def test_prompts_have_invariants() -> None:
    reg = default_prompt_registry()
    for gid in ("parse_task_spec", "vision_extraction", "synthesize_answer"):
        g = reg.get_by_id(gid)
        assert g is not None
        assert len(g.invariants) > 0
