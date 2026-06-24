"""L2 Application use-case — SynthesizeAnswerUseCase (LLM-driven).

Turns a validated TaskGraph + ReasoningResult into a final answer via an LLM.
The LLM is grounded on the validated trajectory (claim texts + fact texts +
goal); it does NOT invent new claims or change statuses.

Anti-fancy invariant: synthesis is gated on ``answer_ready=True`` from
``ReasoningResult``. If the result says ``answer_ready=False`` (ungrounded
claims or unreachable goals), we return a *partial* answer that surfaces
gaps instead of fabricating. The LLM never receives prompts that ask it to
override ungrounded claims.

Pure application. Depends on ports only (R005); no I/O, no activegraph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from active_skill_system.application.ports.llm import LLMMessage, LLMProviderPort
from active_skill_system.application.use_cases.run_reasoning_vertical import (
    ClaimSpec,
    ReasoningResult,
)


@dataclass(frozen=True)
class SynthesizeAnswerRequest:
    """Input to ``SynthesizeAnswerUseCase.run``."""

    goal: str
    facts: tuple[str, ...]
    claims: tuple[ClaimSpec, ...]
    reasoning_result: ReasoningResult


@dataclass(frozen=True)
class SynthesisResult:
    """Output of ``SynthesizeAnswerUseCase.run``."""

    status: str  # "ok" | "partial" (partial = answer_ready was False)
    answer: str
    used_facts: tuple[str, ...] = ()
    used_claims: tuple[str, ...] = ()


_SYSTEM_PROMPT = (
    "You synthesise a final answer from grounded facts and claims. "
    "Do NOT introduce new facts. Do NOT upgrade any claim's certainty. "
    "If the input contains ungrounded claims, surface them as gaps in the "
    "answer; do not paper over them."
)


def _build_user_prompt(req: SynthesizeAnswerRequest) -> str:
    facts_block = "\n".join(f"- {f}" for f in req.facts) or "- (none)"
    claims_block = "\n".join(
        f"- {c.text}"
        + (f"  [evidence: {c.evidence_id}]" if c.evidence_id else "  [UNGROUNDED]")
        for c in req.claims
    ) or "- (none)"
    return (
        f"Goal: {req.goal}\n\n"
        f"Grounded facts:\n{facts_block}\n\n"
        f"Claims (grounding marked explicitly):\n{claims_block}\n\n"
        "Write a concise answer that uses ONLY the grounded facts above. "
        "If there are no grounded facts, write 'Insufficient grounded facts.'\n"
    )


def _partial_answer(req: SynthesizeAnswerRequest) -> SynthesisResult:
    """Build a partial answer without calling the LLM (honest about gaps)."""
    gaps = list(req.reasoning_result.gaps)
    ungrounded = list(req.reasoning_result.ungrounded_claims)
    parts = [f"Partial answer (gaps detected) for goal: {req.goal}"]
    if gaps:
        parts.append("- Gaps (unsupported goal nodes): " + ", ".join(gaps))
    if ungrounded:
        parts.append("- Ungrounded claims: " + ", ".join(ungrounded))
    parts.append(
        "LLM synthesis skipped because the reasoning result is not answer_ready."
    )
    return SynthesisResult(
        status="partial",
        answer="\n".join(parts),
        used_facts=req.facts,
        used_claims=tuple(c.text for c in req.claims if c.evidence_id),
    )


class SynthesizeAnswerUseCase:
    """Synthesise a final answer from a validated trajectory, gated by
    ``answer_ready`` so the LLM never covers ungrounded claims."""

    def __init__(self, llm_provider: LLMProviderPort | None = None) -> None:
        self._llm = llm_provider

    def run(self, request: SynthesizeAnswerRequest) -> SynthesisResult:
        # Anti-fancy gate: if the trajectory is not answer_ready, return
        # an honest partial answer WITHOUT calling the LLM. The LLM is
        # not invited to invent grounded content.
        if not request.reasoning_result.answer_ready:
            return _partial_answer(request)

        if self._llm is None:
            raise RuntimeError(
                "SynthesizeAnswerUseCase requires an LLMProviderPort (R005); "
                "composition must wire MiniMaxProvider or a fake."
            )

        raw = self._llm.complete(
            system=_SYSTEM_PROMPT,
            messages=[LLMMessage(role="user", content=_build_user_prompt(request))],
            model=getattr(self._llm, "default_model", "MiniMax-M3"),
            max_tokens=1024,
            temperature=0.0,
            top_p=1.0,
            output_schema=None,
            timeout_seconds=60.0,
        )
        text = _extract_text(raw)
        return SynthesisResult(
            status="ok",
            answer=text.strip(),
            used_facts=request.facts,
            used_claims=tuple(c.text for c in request.claims if c.evidence_id),
        )


def _extract_text(response: Any) -> str:
    text = getattr(response, "raw_text", None)
    if isinstance(text, str):
        return text
    for attr in ("text", "content"):
        value = getattr(response, attr, None)
        if isinstance(value, str):
            return value
    raise ValueError(f"LLM response had no raw_text/ text attribute (got {type(response).__name__})")
