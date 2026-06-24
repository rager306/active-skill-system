"""L3 Adapter — ActivegraphEventSink (M005 production EventSink impl).

This is the production realisation of the ``EventSink`` port introduced in
M004. It bridges the domain ``TaskGraphBridge`` onto a real ``activegraph.Graph``
by routing every ``emit(event_type, payload)`` through ``graph.emit(Event(...))``.

The sink is intentionally thin:
  - generates a fresh ``Event.id`` (UUID) per emit.
  - sets ``type=event_type`` and ``payload=payload`` (already JSON-friendly).
  - does not depend on any domain types — it speaks the bridge's port.

The replay contract (M005 S02) is: this sink's events are read back via
``graph.events`` (or ``iter_events()``) and fed into
``TaskGraphState.apply_event`` to reconstruct the domain. The S02 tests prove
this end-to-end.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable

from activegraph import Event, Graph


@runtime_checkable
class _EventSinkProtocol(Protocol):
    """The bridge's EventSink contract (re-declared locally to avoid a circular
    import with the bridge module). Real production code uses
    ``taskgraph_bridge.EventSink``; this Protocol keeps type hints usable for
    readers that only need the sink signature."""

    def emit(self, event_type: str, payload: dict[str, Any]) -> None: ...


class ActivegraphEventSink:
    """Production EventSink: bridges ``TaskGraphBridge`` events onto
    ``activegraph.Graph`` via ``graph.emit(Event(...))``.

    Construction is side-effect free (no LLM, no disk, no network). The first
    ``emit`` call is what actually appends to the graph's event log.
    """

    def __init__(self, graph: Graph) -> None:
        if graph is None:
            raise ValueError("ActivegraphEventSink requires a non-None activegraph.Graph")
        self._graph = graph

    @property
    def graph(self) -> Graph:
        """The underlying activegraph graph (exposed for replay tests)."""
        return self._graph

    def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """Append ``(event_type, payload)`` to the graph's event log."""
        if not isinstance(event_type, str) or not event_type:
            raise ValueError(f"event_type must be a non-empty string (got {event_type!r})")
        if not isinstance(payload, dict):
            raise ValueError(f"payload must be a dict (got {type(payload).__name__})")
        event = Event(id=str(uuid.uuid4()), type=event_type, payload=dict(payload))
        self._graph.emit(event)
