"""Integration tests for RunReasoningVerticalUseCase (first Cognitive Runtime vertical).

End-to-end proof of the M003 load-bearing guarantee (anti-fantasy): an
ungrounded claim cannot reach ``answer_ready=True``; it surfaces as a gap /
ungrounded claim instead. Deterministic, no LLM.

Cover:
  - grounded request (fact supports goal + claim with evidence): answer_ready.
  - ungrounded claim (no evidence_id): not answer_ready, claim flagged.
  - unsupported goal (no facts/claims): not answer_ready, goal in gaps.
  - empty goal rejected.
"""

from __future__ import annotations

import pytest

from active_skill_system.application.use_cases.run_reasoning_vertical import (
    ClaimSpec,
    RunReasoningVerticalUseCase,
    TaskSpec,
)


def test_grounded_request_is_answer_ready() -> None:
    """A goal supported by a fact, plus a claim grounded by evidence, is ready."""
    result = RunReasoningVerticalUseCase().run(
        TaskSpec(
            goal="answer the question",
            facts=("accepted fact",),
            claims=(ClaimSpec(text="derived claim", evidence_id="src1"),),
        )
    )
    assert result.answer_ready is True
    assert result.reachable is True
    assert result.ungrounded_claims == ()


def test_ungrounded_claim_blocks_answer() -> None:
    """An ungrounded claim (no evidence_id) is flagged and blocks answer_ready.

    This is the load-bearing anti-fantasy guarantee of M003: the claim cannot
    silently ship as fact.
    """
    result = RunReasoningVerticalUseCase().run(
        TaskSpec(
            goal="answer the question",
            facts=("accepted fact",),
            claims=(ClaimSpec(text="unverified assertion", evidence_id=None),),
        )
    )
    assert result.answer_ready is False
    assert "claim0" in result.ungrounded_claims


def test_unsupported_goal_is_a_gap() -> None:
    """A goal with no supporting facts/claims is not answer_ready and is a gap."""
    result = RunReasoningVerticalUseCase().run(TaskSpec(goal="lonely goal"))
    assert result.answer_ready is False
    assert result.reachable is False
    assert "goal" in result.gaps


def test_claim_grounded_by_evidence_is_not_flagged() -> None:
    """A claim with evidence is grounded and does not appear as ungrounded."""
    result = RunReasoningVerticalUseCase().run(
        TaskSpec(
            goal="g",
            facts=("f",),
            claims=(ClaimSpec(text="c", evidence_id="ev"),),
        )
    )
    assert result.ungrounded_claims == ()
    assert result.answer_ready is True


def test_empty_goal_rejected() -> None:
    """An empty goal is rejected before the graph is built."""
    with pytest.raises(ValueError, match="non-empty"):
        RunReasoningVerticalUseCase().run(TaskSpec(goal="   "))


def test_vertical_use_case_is_infra_free() -> None:
    """The vertical use-case module must not import infrastructure (R002/R004)."""
    import importlib
    from pathlib import Path

    mod = importlib.import_module(
        "active_skill_system.application.use_cases.run_reasoning_vertical"
    )
    assert mod.__file__ is not None
    src = Path(mod.__file__).read_text()
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"run_reasoning_vertical.py must not contain '{forbidden}' (R002)"
