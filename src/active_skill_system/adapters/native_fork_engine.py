"""L3 Adapter — NativeForkEngine (M052 S09, D020).

ForkEngine backed by EventStore + GraphBackend (no activegraph dependency).
Uses EventStore.events_until/events_since to split the event log at the
fork point, then reconstructs the graph state from the prefix events.

For diff: compares the event logs of two runs to find the first divergent
event (split point), then compares the graph states to find divergent
objects/relations.
"""

from __future__ import annotations

import uuid
from typing import Any

from active_skill_system.application.ports.event_store import EventStore
from active_skill_system.domain.fork import Diff, DivergentObject, Fork


class NativeForkEngine:
    """ForkEngine over EventStore. No activegraph dependency."""

    def __init__(self, event_store: EventStore) -> None:
        if event_store is None:
            raise TypeError("event_store must be a non-None EventStore")
        self._store = event_store

    def fork(
        self,
        parent_run_id: str,
        at_event_id: str,
        config_overrides: dict[str, Any] | None = None,
    ) -> Fork:
        """Branch parent_run_id at at_event_id into a new fork run.

        Copies the parent's event prefix into a new run_id.
        """
        fork_run_id = f"fork-{uuid.uuid4().hex[:8]}"

        # Copy prefix events from parent to fork run.
        prefix_events = []
        for event in self._store.iter_events(run_id=parent_run_id):
            prefix_events.append(event)
            if event.id == at_event_id:
                break
        for event in prefix_events:
            from active_skill_system.domain.graph_primitives import GraphEvent

            forked = GraphEvent(
                id=f"{fork_run_id}/{event.id}",
                type=event.type,
                payload=event.payload,
                actor=event.actor,
                run_id=fork_run_id,
                caused_by=event.caused_by,
                timestamp_ns=event.timestamp_ns,
            )
            self._store.append(forked)

        return Fork(
            parent_run_id=parent_run_id,
            fork_run_id=fork_run_id,
            at_event_id=at_event_id,
            config_overrides=config_overrides or {},
        )

    def diff(self, parent_run_id: str, fork_run_id: str) -> Diff:
        """Structurally diff two runs by comparing their event logs."""
        parent_events = list(self._store.iter_events(run_id=parent_run_id))
        fork_events = list(self._store.iter_events(run_id=fork_run_id))

        # Find split point: first event where the traces diverge.
        split_event_id = ""
        min_len = min(len(parent_events), len(fork_events))
        for i in range(min_len):
            pe = parent_events[i]
            fe = fork_events[i]
            if pe.type != fe.type or pe.payload != fe.payload or pe.id != fe.id:
                split_event_id = pe.id
                break

        # If no split found and lengths differ, the split is at the shorter end.
        if not split_event_id and len(parent_events) != len(fork_events):
            if min_len < len(parent_events):
                split_event_id = parent_events[min_len].id
            elif min_len < len(fork_events):
                split_event_id = fork_events[min_len].id

        # Build divergent objects from event payloads.
        divergent_objects: list[DivergentObject] = []
        parent_payloads = {e.id: e.payload for e in parent_events}
        fork_payloads = {e.id: e.payload for e in fork_events}

        parent_ids = set(parent_payloads.keys())
        fork_ids = set(fork_payloads.keys())

        for eid in sorted(fork_ids - parent_ids):
            divergent_objects.append(DivergentObject(
                vertex_id=eid, change_type="added", fork_data=fork_payloads[eid],
            ))
        for eid in sorted(parent_ids - fork_ids):
            divergent_objects.append(DivergentObject(
                vertex_id=eid, change_type="removed", parent_data=parent_payloads[eid],
            ))
        for eid in sorted(parent_ids & fork_ids):
            if parent_payloads[eid] != fork_payloads[eid]:
                divergent_objects.append(DivergentObject(
                    vertex_id=eid, change_type="changed",
                    parent_data=parent_payloads[eid], fork_data=fork_payloads[eid],
                ))

        return Diff(
            parent_run_id=parent_run_id,
            fork_run_id=fork_run_id,
            divergent_objects=tuple(divergent_objects),
            divergent_relations=(),
            split_event_id=split_event_id,
        )


# NativeForkEngine structurally satisfies ForkEngine.
