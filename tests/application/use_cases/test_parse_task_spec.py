"""Unit tests for ParseTaskSpecUseCase (M007 S01, fake-LLM driven).

Drives the LLM-driven parser through a fake ``LLMProviderPort`` so the test
surface is deterministic and infra-free. The parser converts free-text goals
into structured ``TaskSpec`` objects (goal + facts + claims) — the LLM cannot
promote claims (status stays at PROPOSED in the builder, validator gates).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from active_skill_system.application.use_cases.parse_task_spec import (
    ParseTaskSpecRequest,
    ParseTaskSpecUseCase,
)
from active_skill_system.application.use_cases.run_reasoning_vertical import (
    ClaimSpec,
    TaskSpec,
)


@dataclass
class _FakeLLM:
    """Fake LLM that returns a fixed ``raw_text`` (mimics MiniMax/Anthropic)."""

    default_model: str = "fake-mini"
    raw_text: str = ""
    calls: list[dict] = field(default_factory=list)

    def complete(
        self, *, system: str, messages: list, model: str, max_tokens: int,
        temperature: float, top_p: float, output_schema: Any | None,
        timeout_seconds: float, tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        # Record as a normalisable view (role+content) so tests stay readable.
        recorded = []
        for m in messages:
            role = getattr(m, "role", None)
            content = getattr(m, "content", None)
            recorded.append({"role": role, "content": content})
        self.calls.append({"system": system, "messages": recorded})
        return _FakeResponse(self.raw_text)


@dataclass
class _FakeResponse:
    raw_text: str


def test_parse_task_spec_happy_path() -> None:
    llm = _FakeLLM(
        raw_text=json.dumps({
            "goal": "summarise X",
            "facts": ["X is a project", "X started in 2020"],
            "claims": [
                {"text": "X is healthy", "evidence_id": "src1"},
                {"text": "X will grow", "evidence_id": None},
            ],
        })
    )
    spec = ParseTaskSpecUseCase(llm_provider=llm).run(
        ParseTaskSpecRequest(goal="summarise X")
    )
    assert isinstance(spec, TaskSpec)
    assert spec.goal == "summarise X"
    assert spec.facts == ("X is a project", "X started in 2020")
    assert spec.claims == (
        ClaimSpec(text="X is healthy", evidence_id="src1"),
        ClaimSpec(text="X will grow", evidence_id=None),
    )


def test_parse_task_spec_omits_invalid_claim_entries() -> None:
    """Malformed entries are skipped; valid claims survive."""
    llm = _FakeLLM(
        raw_text=json.dumps({
            "goal": "g",
            "facts": [],
            "claims": [
                {"text": "ok", "evidence_id": "src"},
                {"text": "", "evidence_id": "src"},  # empty text: skipped
                "not a dict",  # skipped
                {"text": "no-evidence", "evidence_id": None},
            ],
        })
    )
    spec = ParseTaskSpecUseCase(llm_provider=llm).run(ParseTaskSpecRequest(goal="g"))
    assert spec.claims == (
        ClaimSpec(text="ok", evidence_id="src"),
        ClaimSpec(text="no-evidence", evidence_id=None),
    )


def test_parse_task_spec_strips_code_fence() -> None:
    """If the LLM wraps JSON in ```...```, we still parse it."""
    inner = json.dumps({
        "goal": "g",
        "facts": [],
        "claims": [{"text": "c", "evidence_id": "src"}],
    })
    llm = _FakeLLM(raw_text=f"```json\n{inner}\n```")
    spec = ParseTaskSpecUseCase(llm_provider=llm).run(ParseTaskSpecRequest(goal="g"))
    assert spec.goal == "g"
    assert spec.claims == (ClaimSpec(text="c", evidence_id="src"),)


def test_parse_task_spec_requires_goal() -> None:
    """Empty goal rejected before the LLM is called."""
    llm = _FakeLLM()
    with pytest.raises(ValueError, match="non-empty"):
        ParseTaskSpecUseCase(llm_provider=llm).run(ParseTaskSpecRequest(goal="   "))


def test_parse_task_spec_requires_llm_provider() -> None:
    with pytest.raises(RuntimeError, match="LLMProviderPort"):
        ParseTaskSpecUseCase().run(ParseTaskSpecRequest(goal="g"))


def test_parse_task_spec_malformed_json_raises() -> None:
    import json as _json
    llm = _FakeLLM(raw_text="this is not json at all")
    with pytest.raises(_json.JSONDecodeError):
        ParseTaskSpecUseCase(llm_provider=llm).run(ParseTaskSpecRequest(goal="g"))


def test_parse_task_spec_module_is_infra_free() -> None:
    """R002: use-case source must not contain infra-runtime imports.

    Note: ``LLMMessage`` is now imported from the local
    ``application.ports.llm`` (no activegraph dependency).
    """
    import importlib
    from pathlib import Path

    mod = importlib.import_module(
        "active_skill_system.application.use_cases.parse_task_spec"
    )
    src = Path(mod.__file__).read_text()
    for forbidden in (
        "import activegraph",
        "from activegraph",
        "import anthropic",
        "import openai",
    ):
        assert forbidden not in src, f"parse_task_spec.py must not contain '{forbidden}' (R002)"
