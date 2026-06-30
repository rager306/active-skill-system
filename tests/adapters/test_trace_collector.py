"""Tests for M052 S01 — TraceEnvelope + TraceCollector + InMemoryTraceCollector."""

from __future__ import annotations

import pytest

from active_skill_system.adapters.inmemory_trace_collector import (
    InMemoryTraceCollector,
)
from active_skill_system.application.ports.trace_collector import TraceCollector
from active_skill_system.domain.trace import TraceEnvelope, TraceLayer

# ── TraceEnvelope domain tests ───────────────────────────────────────


def test_trace_envelope_post_init_rejects_empty_trace_id() -> None:
    with pytest.raises(ValueError, match="trace_id must be a non-empty"):
        TraceEnvelope(
            trace_id="", span_id="s1", parent_span_id=None,
            layer="app", operation="op", started_at=0,
        )


def test_trace_envelope_post_init_rejects_empty_span_id() -> None:
    with pytest.raises(ValueError, match="span_id must be a non-empty"):
        TraceEnvelope(
            trace_id="t1", span_id="", parent_span_id=None,
            layer="app", operation="op", started_at=0,
        )


def test_trace_envelope_rejects_ended_before_started() -> None:
    with pytest.raises(ValueError, match="ended_at must be >= started_at"):
        TraceEnvelope(
            trace_id="t1", span_id="s1", parent_span_id=None,
            layer="app", operation="op", started_at=100,
            ended_at=50,
        )


def test_trace_envelope_duration_ms() -> None:
    e = TraceEnvelope(
        trace_id="t1", span_id="s1", parent_span_id=None,
        layer="app", operation="op", started_at=1_000_000,
        ended_at=2_000_000,
    )
    assert e.duration_ms == 1.0


def test_trace_envelope_duration_ms_none_if_open() -> None:
    e = TraceEnvelope(
        trace_id="t1", span_id="s1", parent_span_id=None,
        layer="app", operation="op", started_at=0,
        ended_at=None,
    )
    assert e.duration_ms is None


def test_trace_envelope_new_ids_are_unique() -> None:
    a = TraceEnvelope.new_span_id()
    b = TraceEnvelope.new_span_id()
    assert a != b
    assert a.startswith("span-")


def test_trace_layer_constants() -> None:
    assert TraceLayer.COMPOSITION == "composition"
    assert TraceLayer.APPLICATION == "application"
    assert TraceLayer.ADAPTER == "adapter"


# ── InMemoryTraceCollector tests ─────────────────────────────────────


def test_inmemory_trace_collector_satisfies_protocol() -> None:
    assert isinstance(InMemoryTraceCollector(), TraceCollector)


def test_start_span_returns_span_id() -> None:
    tc = InMemoryTraceCollector()
    sid = tc.start_span("test.op")
    assert sid.startswith("span-")


def test_start_span_generates_trace_id_if_none() -> None:
    tc = InMemoryTraceCollector()
    sid = tc.start_span("test.op")
    span = tc.get_span(sid)
    assert span is not None
    assert span.trace_id.startswith("trace-")


def test_start_span_with_explicit_trace_id() -> None:
    tc = InMemoryTraceCollector()
    sid = tc.start_span("test.op", trace_id="my-trace")
    span = tc.get_span(sid)
    assert span is not None
    assert span.trace_id == "my-trace"


def test_end_span_records_envelope() -> None:
    tc = InMemoryTraceCollector()
    sid = tc.start_span("test.op", model="minimax")
    assert tc.span_count() == 0  # not ended yet
    tc.end_span(sid, status="ok", tokens=100)
    assert tc.span_count() == 1
    span = tc.get_span(sid)
    assert span is not None
    assert span.status == "ok"
    assert span.attributes["model"] == "minimax"
    assert span.attributes["tokens"] == 100
    assert span.ended_at is not None
    assert span.duration_ms is not None


def test_end_span_merges_attributes() -> None:
    tc = InMemoryTraceCollector()
    sid = tc.start_span("op", key1="val1")
    tc.end_span(sid, key2="val2")
    span = tc.get_span(sid)
    assert span is not None
    assert span.attributes == {"key1": "val1", "key2": "val2"}


def test_parent_span_chain() -> None:
    tc = InMemoryTraceCollector()
    parent = tc.start_span("parent.op", trace_id="t1")
    child = tc.start_span("child.op", trace_id="t1", parent_span_id=parent)
    tc.end_span(parent)
    tc.end_span(child)
    parent_span = tc.get_span(parent)
    child_span = tc.get_span(child)
    assert parent_span is not None and child_span is not None
    assert child_span.parent_span_id == parent
    assert parent_span.parent_span_id is None


def test_iter_spans_filters_by_trace_id() -> None:
    tc = InMemoryTraceCollector()
    s1 = tc.start_span("a", trace_id="t1")
    s2 = tc.start_span("b", trace_id="t1")
    s3 = tc.start_span("c", trace_id="t2")
    tc.end_span(s1)
    tc.end_span(s2)
    tc.end_span(s3)
    t1_spans = list(tc.iter_spans("t1"))
    assert len(t1_spans) == 2
    assert all(s.trace_id == "t1" for s in t1_spans)


def test_iter_spans_all_if_no_filter() -> None:
    tc = InMemoryTraceCollector()
    s1 = tc.start_span("a", trace_id="t1")
    s2 = tc.start_span("b", trace_id="t2")
    tc.end_span(s1)
    tc.end_span(s2)
    assert len(list(tc.iter_spans())) == 2


def test_export_writes_json(tmp_path) -> None:  # type: ignore[no-untyped-def]
    tc = InMemoryTraceCollector()
    sid = tc.start_span("test", trace_id="t1")
    tc.end_span(sid, status="ok", model="m")
    export_path = str(tmp_path / "traces.json")
    tc.export(export_path)
    import json

    data = json.loads(open(export_path).read())
    assert len(data) == 1
    assert data[0]["operation"] == "test"
    assert data[0]["attributes"]["model"] == "m"


def test_end_span_unknown_id_is_noop() -> None:
    tc = InMemoryTraceCollector()
    tc.end_span("nonexistent")
    assert tc.span_count() == 0


def test_span_count_only_counts_ended() -> None:
    tc = InMemoryTraceCollector()
    tc.start_span("open1")
    tc.start_span("open2")
    assert tc.span_count() == 0
    # End one
    # (can't — we lost the span_id; test the protocol)
