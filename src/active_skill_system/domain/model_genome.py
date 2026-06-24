"""L1 Domain - ModelGenome value-object (M011, D005).

A typed specification of an LLM model: what it can do (capabilities), how
much context it handles, what it costs, and which provider serves it. This
is the genome for the ``Evolvable`` trait (D004): model-selection evolution
tunes which ModelGenome is used for which pipeline stage.

Pure domain. NO I/O, NO infrastructure imports (R002). Frozen dataclass
with ``__post_init__`` validation. stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ModelCapability(StrEnum):
    """What a model can do (for ModelSelector capability matching)."""

    VISION = "vision"
    THINKING = "thinking"
    TOOLS = "tools"
    STRUCTURED_OUTPUT = "structured_output"
    STREAMING = "streaming"
    FAST = "fast"  # cheap/low-latency tier


@dataclass(frozen=True)
class ModelGenome:
    """Typed specification of an LLM model.

    Carries:
      - id: unique model identifier (e.g. "minimax-m3", "minimax-m2.7-fast").
      - capabilities: what this model can do (non-empty frozenset).
      - context_window: max tokens in context (positive int).
      - cost_input_per_1m: cost in USD per 1M input tokens (non-negative).
      - cost_output_per_1m: cost in USD per 1M output tokens (non-negative).
      - provider_id: which provider/endpoint serves this model (e.g. "router").

    The ``provider_adapter`` (LLMProviderPort instance) is NOT stored here —
    the ModelRegistry maps provider_id → adapter. This keeps the genome
    pure data (no infrastructure references, R002).
    """

    id: str
    capabilities: frozenset[ModelCapability]
    context_window: int
    cost_input_per_1m: float
    cost_output_per_1m: float
    provider_id: str

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.id, str) or not self.id.strip():
            errors.append(f"id must be a non-empty string (got {self.id!r})")
        if not isinstance(self.capabilities, (set, frozenset)) or not self.capabilities:
            errors.append(f"capabilities must be a non-empty frozenset (got {self.capabilities!r})")
        if not isinstance(self.context_window, int) or isinstance(self.context_window, bool):
            errors.append(f"context_window must be an int (got {type(self.context_window).__name__})")
        elif self.context_window <= 0:
            errors.append(f"context_window must be positive (got {self.context_window})")
        for label, val in (
            ("cost_input_per_1m", self.cost_input_per_1m),
            ("cost_output_per_1m", self.cost_output_per_1m),
        ):
            if not isinstance(val, int | float) or val < 0:
                errors.append(f"{label} must be a non-negative number (got {val!r})")
        if not isinstance(self.provider_id, str) or not self.provider_id.strip():
            errors.append(f"provider_id must be a non-empty string (got {self.provider_id!r})")
        if errors:
            raise ValueError(f"ModelGenome({self.id!r}) invariant violation: " + "; ".join(errors))

    def has_capability(self, cap: ModelCapability) -> bool:
        """Check if this model has a given capability."""
        return cap in self.capabilities
