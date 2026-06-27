"""Unit tests for SynthesizeAnswerUseCase (M007 S01).

Anti-fancy gate proven in code: when ``answer_ready=False`` the LLM is NOT
called (the use-case returns an honest partial answer). When answer_ready=True,
the LLM synthesises from grounded facts/claims only — never invents new claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from active_skill_system.application.use_cases.run_reasoning_vertical import (
    ClaimSpec,
    ReasoningResult,
)
from active_skill_system.application.use_cases.synthesize_answer import (
    SynthesisResult,
    SynthesizeAnswerRequest,
    SynthesizeAnswerUseCase,
)


@dataclass
class _FakeLLM:
    default_model: str = "fake"
    raw_text: str = ""
    calls: list[dict] = field(default_factory=list)

    def complete(self, **kwargs: Any) -> Any:
        # Record as a normalisable view (role+content) so tests stay readable.
        recorded = []
        for m in kwargs.get("messages", []):
            role = getattr(m, "role", None)
            content = getattr(m, "content", None)
            recorded.append({"role": role, "content": content})
        kwargs = {**kwargs, "messages": recorded}
        self.calls.append(kwargs)
        return _FakeResponse(self.raw_text)


@dataclass
class _FakeResponse:
    raw_text: str


def _ready_result() -> ReasoningResult:
    return ReasoningResult(
        answer_ready=True,
        reachable=True,
        supported_goals=("goal",),
        gaps=(),
        ungrounded_claims=(),
    )


def _partial_result() -> ReasoningResult:
    return ReasoningResult(
        answer_ready=False,
        reachable=True,
        supported_goals=("goal",),
        gaps=("goal",),
        ungrounded_claims=("claim0",),
    )


def test_synthesize_returns_partial_without_calling_llm_when_not_answer_ready() -> None:
    """Anti-fancy gate: ungrounded → LLM NOT called, partial answer with gaps."""
    llm = _FakeLLM(raw_text="I would fabricate facts here.")
    result = SynthesizeAnswerUseCase(llm_provider=llm).run(
        SynthesizeAnswerRequest(
            goal="g",
            facts=("f1",),
            claims=(ClaimSpec(text="ungrounded", evidence_id=None),),
            reasoning_result=_partial_result(),
        )
    )
    assert isinstance(result, SynthesisResult)
    assert result.status == "partial"
    assert "ungrounded" in result.answer.lower() or "claim0" in result.answer
    assert llm.calls == [], "LLM must not be invoked when answer_ready is False"


def test_synthesize_calls_llm_when_answer_ready() -> None:
    llm = _FakeLLM(raw_text="Based on fact f1, the answer is X.")
    result = SynthesizeAnswerUseCase(llm_provider=llm).run(
        SynthesizeAnswerRequest(
            goal="g",
            facts=("f1", "f2"),
            claims=(ClaimSpec(text="c1", evidence_id="src1"),),
            reasoning_result=_ready_result(),
        )
    )
    assert result.status == "ok"
    assert "answer is X" in result.answer
    assert len(llm.calls) == 1
    user_msg = llm.calls[0]["messages"][0]["content"]
    # The prompt lists facts and marks ungrounded claims explicitly.
    assert "f1" in user_msg
    assert "src1" in user_msg


def test_synthesize_requires_llm_when_answer_ready() -> None:
    with pytest.raises(RuntimeError, match="LLMProviderPort"):
        SynthesizeAnswerUseCase().run(
            SynthesizeAnswerRequest(
                goal="g",
                facts=(),
                claims=(),
                reasoning_result=_ready_result(),
            )
        )


def test_synthesize_partial_surfaces_gaps_and_ungrounded() -> None:
    llm = _FakeLLM(raw_text="would-fabricate")
    result = SynthesizeAnswerUseCase(llm_provider=llm).run(
        SynthesizeAnswerRequest(
            goal="g",
            facts=("f1",),
            claims=(ClaimSpec(text="c-ungrounded", evidence_id=None),),
            reasoning_result=ReasoningResult(
                answer_ready=False,
                reachable=False,
                supported_goals=(),
                gaps=("goal",),
                ungrounded_claims=("c-ungrounded",),
            ),
        )
    )
    assert result.status == "partial"
    assert "goal" in result.answer
    assert "c-ungrounded" in result.answer
