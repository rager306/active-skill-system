"""L3 Adapter — InMemoryTraceCollector (M052 S01, D020).

In-memory trace span collector for tests and ephemeral runs. Thread-safe via
dict operations (GIL-protected). Stores TraceEnvelope objects in a dict keyed
by span_id. No persistence — spans lost when the collector is garbage collected.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from active_skill_system.application.ports.trace_collector import TraceCollector
from active_skill_system.domain.trace import SpanStatus, TraceEnvelope


class InMemoryTraceCollector:
    """TraceCollector backed by an in-memory dict. For tests."""

    def __init__(self) -> None:
        self._spans: dict[str, TraceEnvelope] = {}
        self._open_spans: dict[str, dict[str, Any]] = {}

    def start_span(
        self,
        operation: str,
        *,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        layer: str = "application",
        **attributes: Any,
    ) -> str:
        tid = trace_id or TraceEnvelope.new_trace_id()
        sid = TraceEnvelope.new_span_id()
        now = TraceEnvelope.now_ns()
        self._open_spans[sid] = {
            "trace_id": tid,
            "span_id": sid,
            "parent_span_id": parent_span_id,
            "layer": layer,
            "operation": operation,
            "started_at": now,
            "attributes": dict(attributes),
        }
        return sid

    def end_span(
        self,
        span_id: str,
        *,
        status: str = SpanStatus.OK,
        **attributes: Any,
    ) -> None:
        open_data = self._open_spans.pop(span_id, None)
        if open_data is None:
            return
        merged_attrs = {**open_data["attributes"], **attributes}
        envelope = TraceEnvelope(
            trace_id=open_data["trace_id"],
            span_id=open_data["span_id"],
            parent_span_id=open_data["parent_span_id"],
            layer=open_data["layer"],
            operation=open_data["operation"],
            started_at=open_data["started_at"],
            ended_at=TraceEnvelope.now_ns(),
            status=status,
            attributes=merged_attrs,
        )
        self._spans[span_id] = envelope

    def get_span(self, span_id: str) -> TraceEnvelope | None:
        ended = self._spans.get(span_id)
        if ended is not None:
            return ended
        # Check open spans — return a partial envelope.
        open_data = self._open_spans.get(span_id)
        if open_data is None:
            return None
        return TraceEnvelope(
            trace_id=open_data["trace_id"],
            span_id=open_data["span_id"],
            parent_span_id=open_data["parent_span_id"],
            layer=open_data["layer"],
            operation=open_data["operation"],
            started_at=open_data["started_at"],
            ended_at=None,
            status="open",
            attributes=open_data["attributes"],
        )

    def iter_spans(self, trace_id: str | None = None) -> Iterator[TraceEnvelope]:
        for span in self._spans.values():
            if trace_id is None or span.trace_id == trace_id:
                yield span

    def export(self, path: str) -> None:
        spans = list(self.iter_spans())
        data = [
            {
                "trace_id": s.trace_id,
                "span_id": s.span_id,
                "parent_span_id": s.parent_span_id,
                "layer": s.layer,
                "operation": s.operation,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
                "duration_ms": s.duration_ms,
                "status": s.status,
                "attributes": s.attributes,
            }
            for s in spans
        ]
        Path(path).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def span_count(self) -> int:
        return len(self._spans)


# InMemoryTraceCollector structurally satisfies TraceCollector.
_: TraceCollector = InMemoryTraceCollector()  # type: ignore[assignment]
