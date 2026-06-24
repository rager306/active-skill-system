"""L2 Application — PromptRegistry + PromptRenderer (M012 S02).

PromptRegistry: versioned storage for ``PromptGenome`` instances. Lookup by
id returns the latest version; lookup by id+version returns a specific one.

PromptRenderer: fills template placeholders with slot values, enforcing
required-slot constraints.

Pure application. Depends on domain only (R002).
"""

from __future__ import annotations

from active_skill_system.domain.prompt_genome import PromptGenome


class PromptRegistry:
    """Versioned registry of ``PromptGenome`` instances.

    ``register`` stores the genome keyed by (id, version). ``get_by_id``
    returns the latest version when ``version`` is None.
    """

    def __init__(self) -> None:
        self._genomes: dict[str, dict[int, PromptGenome]] = {}

    def register(self, genome: PromptGenome) -> None:
        """Register a genome. Idempotent on (id, version)."""
        versions = self._genomes.setdefault(genome.id, {})
        versions[genome.version] = genome

    def get_by_id(self, prompt_id: str, version: int | None = None) -> PromptGenome | None:
        """Return the genome, or the latest version if ``version`` is None."""
        versions = self._genomes.get(prompt_id)
        if not versions:
            return None
        if version is not None:
            return versions.get(version)
        # Latest = highest version number.
        return versions[max(versions)]

    def list_all(self) -> tuple[PromptGenome, ...]:
        """Return all registered genomes (all versions)."""
        return tuple(
            genome
            for versions in self._genomes.values()
            for genome in versions.values()
        )


class PromptRenderer:
    """Renders a ``PromptGenome`` template with slot values.

    Required slots must have a value in ``slot_values`` (or a default on the
    slot definition). Optional slots without a value render as empty string.
    """

    def render(self, genome: PromptGenome, slot_values: dict[str, str]) -> str:
        """Fill the template placeholders and return the rendered string."""
        merged: dict[str, str] = {}
        for slot in genome.slots:
            value = slot_values.get(slot.name)
            if value is None:
                if slot.default is not None:
                    value = slot.default
                elif slot.required:
                    raise ValueError(
                        f"PromptRenderer: required slot {slot.name!r} not provided "
                        f"for prompt {genome.id!r}"
                    )
                else:
                    value = ""
            merged[slot.name] = value
        return genome.template.format_map(_SafeDict(merged))


class _SafeDict(dict):
    """dict subclass that returns '' for missing keys (avoids KeyError)."""

    def __missing__(self, key: str) -> str:  # noqa: D401
        return ""
