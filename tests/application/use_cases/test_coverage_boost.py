"""Coverage-boost edge-case tests for application use-cases (M010 S02).

Targets the uncovered lines identified by coverage analysis:
  - extract_facts: retry-backoff, decode fallback, _extract_text fallback attrs
  - parse_task_spec: attachment propagation when vision returns empty, decode error
  - synthesize_answer: _extract_text fallback
  - repair_policy: fallback REPLAN for unknown gap class
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from active_skill_system.application.use_cases.extract_facts import (
    _decode_facts_payload,
    _extract_text,
)
from active_skill_system.application.use_cases.parse_task_spec import (
    ParseTaskSpecRequest,
    ParseTaskSpecUseCase,
)
from active_skill_system.application.use_cases.repair_policy import (
    ActionType,
    RepairPolicy,
)
from active_skill_system.application.use_cases.run_reasoning_vertical import (
    ReasoningResult,
)
from active_skill_system.application.use_cases.synthesize_answer import (
    SynthesizeAnswerRequest,
    SynthesizeAnswerUseCase,
)
from active_skill_system.domain.runtime import (
    MediaRef,
)

# ── extract_facts edge-cases ─────────────────────────────────────────────


def test_decode_facts_payload_strips_code_fence() -> None:
    """Code-fenced JSON is decoded correctly."""
    result = _decode_facts_payload('```json\n{"facts": [{"text": "X", "evidence_id": "e"}]}\n```')
    assert len(result.items) == 1
    assert result.items[0].text == "X"


def test_decode_facts_payload_handles_brace_extraction() -> None:
    """JSON embedded in prose is extracted by brace-matching."""
    result = _decode_facts_payload('Here is the answer: {"facts": [{"text": "Y"}]} thanks')
    assert len(result.items) == 1
    assert result.items[0].text == "Y"


def test_decode_facts_payload_raises_on_unparseable() -> None:
    with pytest.raises(Exception):
        _decode_facts_payload("no json here at all")


def test_decode_facts_payload_skips_invalid_entries() -> None:
    result = _decode_facts_payload('{"facts": [{"text": "ok"}, {"text": ""}, "bad", {"no_text": 1}]}')
    assert len(result.items) == 1
    assert result.items[0].text == "ok"


def test_extract_text_fallback_attrs() -> None:
    """_extract_text falls back to .text/.content if raw_text is missing."""

    @dataclass
    class _Resp:
        text: str = "fallback"

    assert _extract_text(_Resp()) == "fallback"

    @dataclass
    class _Resp2:
        content: str = "content-fallback"

    assert _extract_text(_Resp2()) == "content-fallback"


def test_extract_text_raises_on_no_text_attr() -> None:
    with pytest.raises(ValueError, match="no raw_text"):

        @dataclass
        class _Empty:
            pass

        _extract_text(_Empty())


# ── parse_task_spec edge-cases ────────────────────────────────────────────


@dataclass
class _FakeLLM:
    default_model: str = "fake"
    raw_text: str = '{"goal": "g", "facts": ["f"], "claims": []}'
    calls: int = 0

    def complete(self, **kwargs: Any) -> Any:
        self.calls += 1

        @dataclass
        class R:
            raw_text: str

        return R(self.raw_text)


def test_parse_task_spec_attachments_propagate_without_vision() -> None:
    """Attachments present but no vision_extractor → attachments propagated."""
    llm = _FakeLLM()
    parser = ParseTaskSpecUseCase(llm_provider=llm)  # no vision_extractor
    img = MediaRef(url="https://placehold.co/1x1.png", media_type="image/png")
    spec = parser.run(ParseTaskSpecRequest(goal="g", attachments=(img,)))
    assert len(spec.attachments) == 1
    assert spec.attachments[0].url == "https://placehold.co/1x1.png"


def test_parse_task_spec_rejects_non_tuple_attachments() -> None:
    llm = _FakeLLM()
    parser = ParseTaskSpecUseCase(llm_provider=llm)
    request = ParseTaskSpecRequest(goal="g")
    # Manually set a bad attachments type.
    object.__setattr__(request, "attachments", "not-a-tuple")  # type: ignore[misc]
    with pytest.raises(ValueError, match="attachments"):
        parser.run(request)


# ── synthesize_answer edge-cases ──────────────────────────────────────────


def test_synthesize_extract_text_fallback() -> None:
    """SynthesizeAnswerUseCase falls back to .text attr if raw_text missing."""
    llm = _FakeLLM()

    @dataclass
    class _FallbackLLM:
        default_model: str = "fake"

        def complete(self, **kwargs: Any) -> Any:
            @dataclass
            class R:
                text: str = "fallback-answer"

            return R()

    use_case = SynthesizeAnswerUseCase(llm_provider=_FallbackLLM())
    result = use_case.run(
        SynthesizeAnswerRequest(
            goal="g",
            facts=("f",),
            claims=(),
            reasoning_result=ReasoningResult(
                answer_ready=True, reachable=True, supported_goals=("g",),
                gaps=(), ungrounded_claims=(),
            ),
        )
    )
    assert result.status == "ok"
    assert "fallback" in result.answer


# ── repair_policy edge-cases ──────────────────────────────────────────────


def test_repair_policy_fallback_replan_for_custom_gap_class() -> None:
    """A custom policy missing a gap_class → action_for returns REPLAN."""
    # Create a policy with an empty mapping (will use fallback).
    from active_skill_system.domain.runtime.gap import GapClass as GC

    policy = RepairPolicy(mapping={GC.MISSING_EVIDENCE: ActionType.SEARCH})
    # AMBIGUITY is not in mapping → fallback to REPLAN.
    assert policy.action_for(GC.AMBIGUITY) is ActionType.REPLAN


def test_repair_policy_rejects_empty_mapping() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        RepairPolicy(mapping={})
