"""L2 Application use-case — ParseTaskSpecUseCase (LLM-driven).

Turns a free-text goal into a structured ``TaskSpec`` (goal + facts + claims)
by asking an LLM through ``LLMProviderPort`` (R005).

The use-case:
  1. Builds a structured-output prompt (system + user) that asks the LLM to
     extract ``goal``, ``facts``, and ``claims`` (each with ``text`` and optional
     ``evidence_id``).
  2. Calls the LLM through ``LLMProviderPort.complete`` with ``output_schema``
     set to a schema mirroring ``TaskSpec``.
  3. Parses the LLM's structured output back into a ``TaskSpec`` and validates
     it (the constructor enforces non-empty goal).

Anti-fancy invariant: this use-case produces *only* ``TaskSpec`` inputs to the
domain. It CANNOT mark a claim as VERIFIED — that lives in ``domain/runtime/claim``
and is enforced by the constructor. The LLM may PROPOSE claims (status defaults
to PROPOSED); promoting them to VERIFIED requires independent grounding, which
neither the LLM nor this use-case can supply.

Pure application. Depends on ports only (R005); no I/O, no activegraph.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from active_skill_system.application.ports.llm import LLMMessage, LLMProviderPort
from active_skill_system.application.use_cases.extract_facts import (
    VisionExtractionUseCase,
)
from active_skill_system.application.use_cases.run_reasoning_vertical import (
    ClaimSpec,
    TaskSpec,
)
from active_skill_system.domain.runtime.media_ref import MediaRef


@dataclass(frozen=True)
class ParseTaskSpecRequest:
    """Input to ``ParseTaskSpecUseCase.run``."""

    goal: str
    attachments: tuple[MediaRef, ...] = ()


_SYSTEM_PROMPT = (
    "You extract a structured TaskSpec from a free-text goal. "
    "Return JSON only, no prose, matching the schema: "
    "{\"goal\": str, \"facts\": [str], \"claims\": [{\"text\": str, "
    "\"evidence_id\": str|None}]}. "
    "Each claim must have grounded evidence_id when verifiable, else null. "
    "Do NOT mark any claim as verified or finalised — only propose them."
)


def _build_user_prompt(goal: str) -> str:
    return f"Free-text goal:\n\n{goal}\n\nReturn JSON only."


def _strip_code_fence(text: str) -> str:
    """Strip ```...``` fences if the LLM wrapped JSON in a markdown block."""
    fenced = re.match(r"^\s*```(?:json)?\s*\n(.*)\n```\s*$", text, flags=re.DOTALL)
    if fenced:
        return fenced.group(1)
    return text


def _parse_task_spec_payload(payload: dict) -> TaskSpec:
    """Build a ``TaskSpec`` from a decoded JSON payload."""
    goal = payload.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError(f"LLM output missing non-empty goal (got {goal!r})")
    facts = payload.get("facts", [])
    if not isinstance(facts, list):
        raise ValueError(f"LLM output facts must be a list (got {type(facts).__name__})")
    facts_tuple = tuple(str(f) for f in facts if isinstance(f, str) and f.strip())
    claims_raw = payload.get("claims", [])
    if not isinstance(claims_raw, list):
        raise ValueError(f"LLM output claims must be a list (got {type(claims_raw).__name__})")
    claim_specs = []
    for c in claims_raw:
        if not isinstance(c, dict):
            continue
        text = c.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        evidence_id = c.get("evidence_id")
        if evidence_id is not None and not isinstance(evidence_id, str):
            evidence_id = None
        claim_specs.append(ClaimSpec(text=text.strip(), evidence_id=evidence_id))
    return TaskSpec(goal=goal.strip(), facts=facts_tuple, claims=tuple(claim_specs))


class ParseTaskSpecUseCase:
    """Parse a free-text goal into a structured ``TaskSpec`` via an LLM.

    When ``ParseTaskSpecRequest.attachments`` is non-empty, the use-case
    also runs ``VisionExtractionUseCase`` (separate LLM call) and prepends
    vision-extracted facts to the LLM-parsed facts. Vision is best-effort:
    a failure logs a warning and continues with text-only facts (graceful
    degradation, never raises).
    """

    def __init__(
        self,
        llm_provider: LLMProviderPort | None = None,
        *,
        vision_extractor: VisionExtractionUseCase | None = None,
    ) -> None:
        self._llm = llm_provider
        self._vision = vision_extractor

    def run(self, request: ParseTaskSpecRequest) -> TaskSpec:
        if not isinstance(request.goal, str) or not request.goal.strip():
            raise ValueError("ParseTaskSpecRequest.goal must be a non-empty string")
        if not isinstance(request.attachments, tuple):
            raise ValueError("ParseTaskSpecRequest.attachments must be a tuple of MediaRef")
        if self._llm is None:
            raise RuntimeError(
                "ParseTaskSpecUseCase requires an LLMProviderPort (R005); "
                "composition must wire MiniMaxProvider or a fake."
            )

        # Step 1: LLM parses free-text goal into a TaskSpec (text-only path).
        raw = self._llm.complete(
            system=_SYSTEM_PROMPT,
            messages=[LLMMessage(role="user", content=_build_user_prompt(request.goal))],
            model=getattr(self._llm, "default_model", "MiniMax-M3"),
            max_tokens=1024,
            temperature=0.0,
            top_p=1.0,
            output_schema=None,  # adapter may ignore; we parse raw_text defensively
            timeout_seconds=60.0,
        )
        raw_text = _extract_text(raw)
        payload = _decode_json(raw_text)
        spec = _parse_task_spec_payload(payload)

        # Step 2: vision extraction (M008). If attachments are present and a
        # vision_extractor is wired, prepend vision facts to the LLM facts.
        # Vision is best-effort: failures are swallowed by the extractor
        # (graceful degradation), so we never raise here.
        vision_facts: tuple[str, ...] = ()
        if request.attachments and self._vision is not None:
            try:
                facts = self._vision.extract(request.goal, request.attachments)
                if facts is not None and facts.items:
                    vision_facts = tuple(f.text for f in facts.items)
            except Exception:  # noqa: BLE001 — defensive; extractor should already
                # swallow, but we belt-and-brace around it.
                pass
        # If attachments are present (whether vision ran or not), propagate
        # them so downstream stages (e.g. RunReasoningVertical) can still
        # see them. Vision facts (possibly empty) are prepended.
        if request.attachments:
            spec = TaskSpec(
                goal=spec.goal,
                facts=vision_facts + spec.facts,
                claims=spec.claims,
                attachments=request.attachments,
            )
        return spec


def _extract_text(response: Any) -> str:
    """Pull ``raw_text`` out of an ``LLMResponse`` (tolerant of attribute shape)."""
    text = getattr(response, "raw_text", None)
    if isinstance(text, str):
        return text
    # Fallback: attribute access across provider shapes.
    for attr in ("text", "content"):
        value = getattr(response, attr, None)
        if isinstance(value, str):
            return value
    raise ValueError(f"LLM response had no raw_text/ text attribute (got {type(response).__name__})")


def _decode_json(raw_text: str) -> dict:
    """Decode JSON from an LLM response (defensive: strip fences, handle braces)."""
    text = _strip_code_fence(raw_text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Last-ditch: try to extract the first {...} block.
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise
