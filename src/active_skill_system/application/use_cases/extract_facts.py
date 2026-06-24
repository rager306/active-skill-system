"""L2 Application use-case — VisionExtractionUseCase (M008).

Extracts structured text facts from images via an LLM. The use-case
projects multimodal input to plain text — the domain stays text-only
(anti-fancy gating is preserved end-to-end).

Reliability:
  * **Retry with exponential backoff** on transient LLM errors (3 tries,
    1s / 2s / 4s + small jitter). A real gateway flake should be retried,
    not surfaced.
  * **Graceful degradation** on persistent failure: log a warning and
    return ``Facts()`` (empty). The caller can still proceed with the
    LLM's text-only parse; vision is best-effort.

The use-case is pure (no I/O outside LLM call), domain-infra-free
(``MediaRef`` is a local domain type), and goes through ``LLMProviderPort``
(R005) — the LLM call is text-only from the domain's point of view.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Any

from active_skill_system.application.ports.llm import LLMMessage, LLMProviderPort
from active_skill_system.domain.runtime.media_ref import MediaRef

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "You extract structured facts from images. Return JSON only, no prose, "
    "matching the schema: {\"facts\": [{\"text\": str, \"evidence_id\": str|None}]}. "
    "Each fact must be a single observable claim grounded in the image. "
    "Do not introduce new facts. Do not upgrade any claim's certainty."
)


# Retry policy (3 attempts; backoff with jitter).
_RETRY_BACKOFFS_SEC = (1.0, 2.0, 4.0)
_JITTER_FRACTION = 0.2


@dataclass(frozen=True)
class Fact:
    """One structured fact extracted from an image."""

    text: str
    evidence_id: str | None = None


@dataclass(frozen=True)
class Facts:
    """Vision extraction result: a list of facts (may be empty)."""

    items: tuple[Fact, ...] = ()


def _build_user_prompt(goal: str) -> str:
    return f"Goal: {goal}\n\nReturn JSON: {{\"facts\": [{{\"text\": \"...\", \"evidence_id\": \"...\"}}]}}"


def _build_messages(goal: str, images: tuple[MediaRef, ...]) -> list[LLMMessage]:
    """Build the multimodal message list (text + images) for the LLM call."""
    user_text = _build_user_prompt(goal)
    content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    for img in images:
        content.append(
            {
                "type": "image",
                "source": {"type": "url", "url": img.url},
            }
        )
    return [LLMMessage(role="user", content=json.dumps(content))]


def _strip_code_fence(text: str) -> str:
    fenced = re.match(r"^\s*```(?:json)?\s*\n(.*)\n```\s*$", text, flags=re.DOTALL)
    if fenced:
        return fenced.group(1)
    return text


def _decode_facts_payload(raw_text: str) -> Facts:
    """Decode JSON payload into ``Facts``. Defensive against code-fence wrappers."""
    text = _strip_code_fence(raw_text).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            payload = json.loads(text[start : end + 1])
        else:
            raise
    raw_facts = payload.get("facts", [])
    if not isinstance(raw_facts, list):
        raise ValueError(f"vision payload 'facts' must be a list (got {type(raw_facts).__name__})")
    items: list[Fact] = []
    for f in raw_facts:
        if not isinstance(f, dict):
            continue
        text = f.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        evidence_id = f.get("evidence_id")
        if evidence_id is not None and not isinstance(evidence_id, str):
            evidence_id = None
        items.append(Fact(text=text.strip(), evidence_id=evidence_id))
    return Facts(items=tuple(items))


def _extract_text(response: Any) -> str:
    text = getattr(response, "raw_text", None)
    if isinstance(text, str):
        return text
    for attr in ("text", "content"):
        value = getattr(response, attr, None)
        if isinstance(value, str):
            return value
    raise ValueError(
        f"LLM response had no raw_text/ text attribute (got {type(response).__name__})"
    )


class VisionExtractionUseCase:
    """Extract structured text facts from images via the LLM.

    ``images`` is a tuple of ``MediaRef`` references (URLs validated by the
    domain). The LLM call is the only network surface; everything else is
    pure. On persistent failure the use-case returns empty ``Facts()`` and
    logs a warning (graceful degradation, NOT an exception).
    """

    def __init__(
        self,
        llm_provider: LLMProviderPort | None = None,
        *,
        max_attempts: int = 3,
    ) -> None:
        self._llm = llm_provider
        self._max_attempts = max(1, max_attempts)

    def extract(self, goal: str, images: tuple[MediaRef, ...]) -> Facts:
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("goal must be a non-empty string")
        if not images:
            return Facts()  # no images, nothing to extract
        if self._llm is None:
            raise RuntimeError(
                "VisionExtractionUseCase requires an LLMProviderPort (R005); "
                "composition must wire MiniMaxProvider or a fake."
            )

        messages = _build_messages(goal, images)
        model = getattr(self._llm, "default_model", "MiniMax-M3")

        for attempt in range(1, self._max_attempts + 1):
            try:
                raw = self._llm.complete(
                    system=_SYSTEM_PROMPT,
                    messages=messages,
                    model=model,
                    max_tokens=1024,
                    temperature=0.0,
                    top_p=1.0,
                    output_schema=None,
                    timeout_seconds=60.0,
                )
                return _decode_facts_payload(_extract_text(raw))
            except Exception as e:  # noqa: BLE001 — best-effort, log + retry
                if attempt >= self._max_attempts:
                    logger.warning(
                        "VisionExtractionUseCase: persistent failure after %d "
                        "attempts; returning empty Facts (graceful degradation). "
                        "goal=%r images=%d err=%s",
                        attempt,
                        goal,
                        len(images),
                        e,
                    )
                    return Facts()
                backoff = _RETRY_BACKOFFS_SEC[min(attempt - 1, len(_RETRY_BACKOFFS_SEC) - 1)]
                jitter = backoff * _JITTER_FRACTION * (2 * random.random() - 1)
                sleep_for = max(0.0, backoff + jitter)
                logger.info(
                    "VisionExtractionUseCase: attempt %d/%d failed (err=%s); "
                    "retrying in %.2fs",
                    attempt,
                    self._max_attempts,
                    e,
                    sleep_for,
                )
                time.sleep(sleep_for)
        # Defensive; loop returns on success or empty Facts on exhaustion.
        return Facts()
