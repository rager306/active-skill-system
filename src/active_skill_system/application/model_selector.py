"""L2 Application — ModelSelector (M011 S02).

Selects the best ``ModelGenome`` for a given pipeline stage and set of
required capabilities. Implements per-stage routing (D005):
  parse            → prefer FAST
  vision_extraction → require VISION
  synthesize       → prefer THINKING
  repair           → prefer TOOLS
  default          → first available

Pure application. Depends on domain + registry; no I/O (R002).
"""

from __future__ import annotations

from enum import StrEnum

from active_skill_system.application.model_registry import ModelRegistry
from active_skill_system.domain.model_genome import ModelCapability, ModelGenome


class StageType(StrEnum):
    """Pipeline stage for model selection."""

    PARSE = "parse"
    VISION_EXTRACTION = "vision_extraction"
    SYNTHESIZE = "synthesize"
    REPAIR = "repair"
    DEFAULT = "default"


# Per-stage preferred capability (tie-breaker after required caps are met).
_STAGE_PREFERENCE: dict[StageType, ModelCapability] = {
    StageType.PARSE: ModelCapability.FAST,
    StageType.VISION_EXTRACTION: ModelCapability.VISION,
    StageType.SYNTHESIZE: ModelCapability.THINKING,
    StageType.REPAIR: ModelCapability.TOOLS,
}


class ModelSelector:
    """Select the best model for a stage given required capabilities.

    Selection algorithm:
      1. Filter registry: only models that have ALL required capabilities.
      2. If none match: return None.
      3. Prefer models that also have the stage-preference capability.
      4. Among matches: prefer the cheapest (lowest total cost per 1M).
    """

    def select(
        self,
        stage: StageType,
        required_capabilities: frozenset[ModelCapability],
        registry: ModelRegistry,
    ) -> ModelGenome | None:
        """Return the best ModelGenome for the stage, or None if no match."""
        # Step 1: filter by required capabilities.
        if required_capabilities:
            candidates: list[ModelGenome] = []
            for genome in registry.list_all():
                if all(genome.has_capability(cap) for cap in required_capabilities):
                    candidates.append(genome)
        else:
            candidates = list(registry.list_all())

        if not candidates:
            return None

        # Step 2: prefer models with the stage-preference capability.
        preference = _STAGE_PREFERENCE.get(stage)
        if preference:
            preferred = [g for g in candidates if g.has_capability(preference)]
            if preferred:
                candidates = preferred

        # Step 3: cheapest among the remaining candidates.
        return min(candidates, key=lambda g: g.cost_input_per_1m + g.cost_output_per_1m)
