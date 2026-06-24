"""L1 Domain - PromptGenome value-object (M012, D004 Evolvable).

A versioned, immutable specification of an LLM prompt template with named
slots. The first concrete ``Evolvable`` artifact (D004): prompts can be
mutated, evaluated offline, and promoted through a ratchet.

Pure domain. NO I/O, NO infrastructure imports (R002). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSlot:
    """A named placeholder in a prompt template.

    Carries:
      - name: the slot identifier (used in template as ``{name}``).
      - required: if True, the renderer must receive a value for this slot.
      - default: optional default value when the slot is not provided.
    """

    name: str
    required: bool = True
    default: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(f"PromptSlot.name must be a non-empty string (got {self.name!r})")


@dataclass(frozen=True)
class PromptGenome:
    """A versioned prompt template with named slots.

    Carries:
      - id: unique prompt identifier (e.g. "parse_task_spec").
      - template: the prompt text with ``{slot_name}`` placeholders.
      - slots: tuple of PromptSlot definitions.
      - version: monotonic version counter (starts at 1).
      - invariants: documentation of constraints the prompt must satisfy.
    """

    id: str
    template: str
    slots: tuple[PromptSlot, ...]
    version: int = 1
    invariants: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.id, str) or not self.id.strip():
            errors.append(f"id must be a non-empty string (got {self.id!r})")
        if not isinstance(self.template, str) or not self.template.strip():
            errors.append(f"template must be a non-empty string (got {len(self.template)} chars)")
        if not isinstance(self.slots, tuple) or len(self.slots) == 0:
            errors.append(f"slots must be a non-empty tuple (got {self.slots!r})")
        if not isinstance(self.version, int) or self.version < 1:
            errors.append(f"version must be a positive int (got {self.version})")
        if errors:
            raise ValueError(f"PromptGenome({self.id!r}) invariant violation: " + "; ".join(errors))

    def slot_names(self) -> tuple[str, ...]:
        """Return the names of all slots in order."""
        return tuple(s.name for s in self.slots)
