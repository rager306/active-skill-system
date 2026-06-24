"""L2 Application — ModelRegistry (M011 S02).

Maps ``ModelGenome`` ids to genome instances and supports capability-based
lookup. The registry is the data backing for ``ModelSelector``; it does not
hold provider-adapter instances (those live in composition, keyed by
``provider_id``).

Pure application. Depends on domain only (R002).
"""

from __future__ import annotations

from active_skill_system.domain.model_genome import ModelCapability, ModelGenome


class ModelRegistry:
    """Registry of ``ModelGenome`` instances, lookupable by id or capability.

    Usage::

        reg = ModelRegistry()
        reg.register(m3_genome)
        reg.register(m2_7_genome)
        vision_models = reg.list_by_capability(ModelCapability.VISION)
    """

    def __init__(self) -> None:
        self._genomes: dict[str, ModelGenome] = {}

    def register(self, genome: ModelGenome) -> None:
        """Register a genome. Idempotent on ``genome.id`` (re-register replaces)."""
        self._genomes[genome.id] = genome

    def get_by_id(self, model_id: str) -> ModelGenome | None:
        """Return the genome with the given id, or None."""
        return self._genomes.get(model_id)

    def list_by_capability(self, cap: ModelCapability) -> tuple[ModelGenome, ...]:
        """Return all genomes that have the given capability."""
        return tuple(g for g in self._genomes.values() if g.has_capability(cap))

    def list_all(self) -> tuple[ModelGenome, ...]:
        """Return all registered genomes."""
        return tuple(self._genomes.values())
