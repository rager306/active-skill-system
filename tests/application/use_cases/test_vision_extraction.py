"""Unit tests for VisionExtractionUseCase + integration with ParseTaskSpec
and RunReasoningVertical (M008 S02)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from active_skill_system.application.use_cases.extract_facts import (
    Fact,
    Facts,
    VisionExtractionUseCase,
)
from active_skill_system.application.use_cases.parse_task_spec import (
    ParseTaskSpecRequest,
    ParseTaskSpecUseCase,
)
from active_skill_system.application.use_cases.run_reasoning_vertical import (
    RunReasoningVerticalUseCase,
    TaskSpec,
)
from active_skill_system.domain.runtime import NodeKind
from active_skill_system.domain.runtime.media_ref import MediaRef


# ── fake LLM ──────────────────────────────────────────────────────────────


@dataclass
class _FakeLLM:
    """Fake LLM that returns a fixed ``raw_text`` (or raises)."""

    default_model: str = "fake"
    raw_text: str = ""
    raise_with: Exception | None = None
    call_count: int = field(default=0, init=False)

    def complete(
        self, *, system: str, messages: list, model: str, max_tokens: int,
        temperature: float, top_p: float, output_schema: Any | None,
        timeout_seconds: float, tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        self.call_count += 1
        if self.raise_with is not None:
            raise self.raise_with
        return _FakeResponse(self.raw_text)


@dataclass
class _FakeResponse:
    raw_text: str


def _image() -> MediaRef:
    return MediaRef(url="https://placehold.co/1x1.png", media_type="image/png")


# ── VisionExtractionUseCase: success / parse / no-op / retry / graceful ──


def test_extract_returns_empty_when_no_images() -> None:
    """No images → no work → empty Facts (no LLM call)."""
    llm = _FakeLLM()
    result = VisionExtractionUseCase(llm_provider=llm).extract("g", ())
    assert result.items == ()
    assert llm.call_count == 0


def test_extract_parses_structured_facts() -> None:
    import json as _json

    llm = _FakeLLM(
        raw_text=_json.dumps({
            "facts": [
                {"text": "Y is true", "evidence_id": "src1"},
                {"text": "Z is observed", "evidence_id": None},
            ],
        })
    )
    result = VisionExtractionUseCase(llm_provider=llm).extract("g", (_image(),))
    assert len(result.items) == 2
    assert result.items[0] == Fact(text="Y is true", evidence_id="src1")
    assert result.items[1] == Fact(text="Z is observed", evidence_id=None)


def test_extract_strips_code_fence() -> None:
    llm = _FakeLLM(raw_text='```json\n{"facts": [{"text": "X", "evidence_id": "e"}]}\n```')
    result = VisionExtractionUseCase(llm_provider=llm).extract("g", (_image(),))
    assert result.items == (Fact(text="X", evidence_id="e"),)


def test_extract_retries_then_succeeds(monkeypatch) -> None:  # noqa: ANN001
    """Transient ConnectionError 2 times → 3rd attempt succeeds."""
    import time as _time

    monkeypatch.setattr(_time, "sleep", lambda _: None)  # skip real sleep
    call = {"n": 0}

    def _flaky(**kwargs: Any) -> Any:
        call["n"] += 1
        if call["n"] < 3:
            raise ConnectionError("transient")
        return _FakeResponse('{"facts": [{"text": "ok", "evidence_id": "e"}]}')

    llm = _FakeLLM()
    llm.raise_with = None
    llm.complete = _flaky  # type: ignore[method-assign]
    result = VisionExtractionUseCase(llm_provider=llm, max_attempts=3).extract("g", (_image(),))
    assert call["n"] == 3
    assert result.items == (Fact(text="ok", evidence_id="e"),)


def test_extract_graceful_degradation_after_persistent_failure(monkeypatch) -> None:  # noqa: ANN001
    """3 attempts all fail → returns empty Facts() (graceful), no exception."""
    import time as _time

    monkeypatch.setattr(_time, "sleep", lambda _: None)
    llm = _FakeLLM(raise_with=ConnectionError("down"))
    result = VisionExtractionUseCase(llm_provider=llm, max_attempts=3).extract(
        "g", (_image(),)
    )
    assert result == Facts()
    assert llm.call_count == 3


def test_extract_requires_llm_provider() -> None:
    with pytest.raises(RuntimeError, match="LLMProviderPort"):
        VisionExtractionUseCase().extract("g", (_image(),))


# ── ParseTaskSpecUseCase: attachments + vision ───────────────────────────


@dataclass
class _TwoStageLLM:
    """Fake LLM: parse stage returns a fact; vision stage returns a vision fact."""

    default_model: str = "fake"
    parse_text: str = '{"goal": "g", "facts": ["text-fact"], "claims": []}'
    vision_text: str = '{"facts": [{"text": "vision-fact", "evidence_id": "e1"}]}'
    parse_calls: int = field(default=0, init=False)
    vision_calls: int = field(default=0, init=False)

    def complete(self, **kwargs: Any) -> Any:
        sys = kwargs.get("system", "")
        if "structured facts from images" in sys:
            self.vision_calls += 1
            return _FakeResponse(self.vision_text)
        self.parse_calls += 1
        return _FakeResponse(self.parse_text)


def test_parse_task_spec_with_attachments_prepends_vision_facts() -> None:
    llm = _TwoStageLLM()
    vision = VisionExtractionUseCase(llm_provider=llm)
    parser = ParseTaskSpecUseCase(llm_provider=llm, vision_extractor=vision)
    spec = parser.run(
        ParseTaskSpecRequest(goal="g", attachments=(_image(),))
    )
    # Vision fact came first; parse fact followed.
    assert spec.facts == ("vision-fact", "text-fact")
    assert spec.attachments == (_image(),)
    assert llm.parse_calls == 1
    assert llm.vision_calls == 1


def test_parse_task_spec_without_attachments_skips_vision() -> None:
    llm = _TwoStageLLM()
    vision = VisionExtractionUseCase(llm_provider=llm)
    parser = ParseTaskSpecUseCase(llm_provider=llm, vision_extractor=vision)
    spec = parser.run(ParseTaskSpecRequest(goal="g"))
    assert spec.facts == ("text-fact",)
    assert spec.attachments == ()
    assert llm.vision_calls == 0


def test_parse_task_spec_vision_failure_does_not_block_parse() -> None:
    """Vision fails (graceful) → text-only path continues; attachments preserved."""

    @dataclass
    class _SplitLLM:
        default_model: str = "fake"
        parse_text: str = '{"goal": "g", "facts": ["text-only"], "claims": []}'

        def complete(self, **kwargs: Any) -> Any:
            sys = kwargs.get("system", "")
            if "structured facts from images" in sys:
                raise ConnectionError("vision down")
            return _FakeResponse(self.parse_text)

    llm = _SplitLLM()
    vision = VisionExtractionUseCase(llm_provider=llm, max_attempts=1)
    parser = ParseTaskSpecUseCase(llm_provider=llm, vision_extractor=vision)
    spec = parser.run(
        ParseTaskSpecRequest(goal="g", attachments=(_image(),))
    )
    assert spec.facts == ("text-only",)
    # attachments preserved even if vision failed (length-check; new MediaRef
    # instances compare by value but constructing a fresh tuple for equality
    # is brittle here).
    assert len(spec.attachments) == 1
    assert spec.attachments[0].url == _image().url


# ── RunReasoningVerticalUseCase: MediaRef → Evidence-узлы ────────────────


def test_vertical_runs_with_attachments() -> None:
    """RunReasoningVertical accepts a TaskSpec with attachments and
    returns a valid ReasoningResult. The attachment is projected as an
    Evidence-узел in the graph; for this test we just verify the pipeline
    succeeds end-to-end (no exceptions) and answer_ready reflects the
    validated trajectory (goal + 1 fact → reachable, no ungrounded
    claims, no constraints → answer_ready=True)."""
    spec = TaskSpec(
        goal="g",
        facts=("extracted fact",),
        claims=(),
        attachments=(_image(),),
    )
    result = RunReasoningVerticalUseCase().run(spec)
    assert result.reachable is True
    assert result.answer_ready is True
    # No ungrounded claims: the only fact is grounded by being a text Fact.
    assert result.ungrounded_claims == ()
