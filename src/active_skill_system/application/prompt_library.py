"""L2 Application — default prompt library (M012 S03).

Registers existing system prompts (parse, vision, synthesize) as
``PromptGenome`` instances in a ``PromptRegistry``, making them versioned
and auditable. This is the wiring step that connects the PromptGenome
infrastructure (S01-S02) to the real system prompts used by use-cases.

Pure application. Depends on domain + prompt_registry (R002).
"""

from __future__ import annotations

from active_skill_system.application.prompt_registry import PromptRegistry
from active_skill_system.domain.prompt_genome import PromptGenome, PromptSlot


def default_prompt_registry() -> PromptRegistry:
    """Return a PromptRegistry with the system prompts registered.

    The templates mirror the ``_SYSTEM_PROMPT`` constants already used by
    ParseTaskSpecUseCase, VisionExtractionUseCase, and SynthesizeAnswerUseCase.
    Future versions can be added alongside v1 without breaking callers.
    """
    reg = PromptRegistry()

    # --- parse_task_spec v1 ---
    reg.register(
        PromptGenome(
            id="parse_task_spec",
            template=(
                "You extract a structured TaskSpec from a free-text goal. "
                "Return JSON only, no prose, matching the schema: "
                '{{"goal": str, "facts": [str], "claims": [{{"text": str, '
                '"evidence_id": str|None}}]}}. '
                "Each claim must have grounded evidence_id when verifiable, else null. "
                "Do NOT mark any claim as verified or finalised — only propose them. "
                "Goal: {goal}"
            ),
            slots=(PromptSlot(name="goal"),),
            version=1,
            invariants=("output_must_be_json", "no_verified_claims"),
        )
    )

    # --- vision_extraction v1 ---
    reg.register(
        PromptGenome(
            id="vision_extraction",
            template=(
                "You extract structured facts from images. Return JSON only, "
                'no prose, matching the schema: {{"facts": [{{"text": str, '
                '"evidence_id": str|None}}]}}. '
                "Each fact must be a single observable claim grounded in the image. "
                "Do not introduce new facts. Do not upgrade any claim's certainty. "
                "Goal: {goal}"
            ),
            slots=(PromptSlot(name="goal"),),
            version=1,
            invariants=("output_must_be_json", "facts_from_image_only"),
        )
    )

    # --- synthesize_answer v1 ---
    reg.register(
        PromptGenome(
            id="synthesize_answer",
            template=(
                "You synthesise a final answer from grounded facts and claims. "
                "Do NOT introduce new facts. Do NOT upgrade any claim's certainty. "
                "If the input contains ungrounded claims, surface them as gaps "
                "in the answer; do not paper over them.\n"
                "Goal: {goal}\n"
                "Grounded facts:\n{facts}\n"
                "Claims:\n{claims}"
            ),
            slots=(
                PromptSlot(name="goal"),
                PromptSlot(name="facts"),
                PromptSlot(name="claims"),
            ),
            version=1,
            invariants=("no_new_facts", "no_certainty_upgrade"),
        )
    )

    return reg
