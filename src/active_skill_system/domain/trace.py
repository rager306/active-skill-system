"""L1 Domain — TraceEnvelope (M052 S01, D020).

A traced operation spanning multiple architectural layers. Carries causality
(parent_span_id) for reconstructing ordering across layers and across async
operations. This is our distributed tracing primitive — it answers "WHY did
this happen?" (causality chain) in addition to "WHAT happened?" (event log).

Pure domain. NO I/O, NO infrastructure imports (R002/R003). stdlib only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


class TraceLayer:
    """Well-known architectural layer labels for trace spans."""

    COMPOSITION = "composition"
    APPLICATION = "application"
    ADAPTER = "adapter"
    DOMAIN = "domain"


class SpanStatus:
    """Span completion status."""

    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class TraceEnvelope:
    """One traced operation (span) in a distributed trace.

    Fields:
      - trace_id: unique per top-level operation (e.g. one sandbox run).
      - span_id: unique per sub-operation (e.g. one LLM call, one graph query).
      - parent_span_id: causality chain (None for root span).
      - layer: which architectural layer (composition/application/adapter).
      - operation: what happened (e.g. "llm.complete", "graph.upsert", "verify").
      - started_at: nanosecond timestamp when span started.
      - ended_at: nanosecond timestamp when span ended (None if open).
      - status: ok / error / timeout.
      - attributes: structured key-value (model, tokens, exit_code, etc.).
    """

    trace_id: str
    span_id: str
    parent_span_id: str | None
    layer: str
    operation: str
    started_at: int
    ended_at: int | None = None
    status: str = SpanStatus.OK
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.trace_id, str) or not self.trace_id.strip():
            errors.append(f"trace_id must be a non-empty string (got {self.trace_id!r})")
        if not isinstance(self.span_id, str) or not self.span_id.strip():
            errors.append(f"span_id must be a non-empty string (got {self.span_id!r})")
        if not isinstance(self.layer, str) or not self.layer.strip():
            errors.append(f"layer must be a non-empty string (got {self.layer!r})")
        if not isinstance(self.operation, str) or not self.operation.strip():
            errors.append(f"operation must be a non-empty string (got {self.operation!r})")
        if not isinstance(self.started_at, int) or self.started_at < 0:
            errors.append(f"started_at must be a non-negative int (got {self.started_at!r})")
        if self.ended_at is not None and (not isinstance(self.ended_at, int) or self.ended_at < self.started_at):
            errors.append(f"ended_at must be >= started_at (got {self.ended_at!r})")
        if not isinstance(self.attributes, dict):
            errors.append(f"attributes must be a dict (got {type(self.attributes).__name__})")
        if errors:
            raise ValueError("TraceEnvelope invariant violation: " + "; ".join(errors))

    @property
    def duration_ms(self) -> float | None:
        """Duration in milliseconds, or None if span is still open."""
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at) / 1_000_000

    @staticmethod
    def new_span_id() -> str:
        """Generate a unique span id."""
        return f"span-{uuid.uuid4().hex[:12]}"

    @staticmethod
    def new_trace_id() -> str:
        """Generate a unique trace id."""
        return f"trace-{uuid.uuid4().hex[:12]}"

    @staticmethod
    def now_ns() -> int:
        """Current time in nanoseconds."""
        return int(datetime.now(UTC).timestamp() * 1_000_000_000)
