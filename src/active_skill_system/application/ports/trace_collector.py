"""L2 Application — TraceCollector port (M052 S01, D020).

Distributed tracing port for debugging reactive/async processes. Collects
trace spans across architectural layers (composition → application → adapter).
Each span carries causality (parent_span_id) for reconstructing ordering.

Adapters:
  - InMemoryTraceCollector — tests, default.
  - EventStoreTraceCollector — persists spans to EventStore (M051).
  - OpenTelemetryTraceCollector — future, for OTLP export.

Pure application (R002): depends only on domain TraceEnvelope type.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol, runtime_checkable

from active_skill_system.domain.trace import TraceEnvelope


@runtime_checkable
class TraceCollector(Protocol):
    """Distributed trace span collector.

    Implementations MUST be thread-safe if used from async/concurrent code.
    start_span returns immediately (does not block). end_span records the
    completed span. export writes the full trace to a file.
    """

    def start_span(
        self,
        operation: str,
        *,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        layer: str = "application",
        **attributes: Any,
    ) -> str:
        """Start a new span. Returns span_id.

        If trace_id is None, a new trace_id is generated (root span).
        If parent_span_id is given, this span is a child of that span.
        """
        ...

    def end_span(
        self,
        span_id: str,
        *,
        status: str = "ok",
        **attributes: Any,
    ) -> None:
        """End a span by span_id. Records timing + status."""
        ...

    def get_span(self, span_id: str) -> TraceEnvelope | None:
        """Return the span envelope, or None if not found."""
        ...

    def iter_spans(self, trace_id: str | None = None) -> Iterator[TraceEnvelope]:
        """Iterate spans. If trace_id given, filter to that trace."""
        ...

    def export(self, path: str) -> None:
        """Export all spans (or one trace) to a JSON file."""
        ...

    def span_count(self) -> int:
        """Total number of spans collected."""
        ...
