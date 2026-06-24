"""L1 Domain - GraphPatch and measurable-improvement gate (M009, concept.md §7).

A ``GraphPatch`` is a set of reversible operations applied to a ``TaskGraph``
to close a gap. concept.md §7 mandatory limiters:

> новая версия графа принимается, если:
>   critical_gaps уменьшились OR reachability выросла OR verified goals ↑
>   при этом:
>     hard_constraint_violations не выросли AND risk не ухудшился

``is_measurable_improvement`` encodes that gate as a pure function over
integer counts (before vs after), keeping the domain free of any dependency
on the application-layer ``ValidationReport``.

Pure domain. NO I/O, NO infrastructure imports (R002). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from active_skill_system.domain.runtime.edges import EdgeKind, TaskEdge
from active_skill_system.domain.runtime.graph import TaskGraph
from active_skill_system.domain.runtime.nodes import NodeKind, TaskNode, TaskNodeId

# ── GraphPatch ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PatchOp:
    """A single reversible operation in a GraphPatch.

    op_type:
      - "add_node":           payload has node_id, kind, text, (optional) media fields.
      - "add_edge":           payload has source, target, kind.
      - "update_claim_status": payload has claim_id, new_status (str).
    """

    op_type: str
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.op_type, str) or not self.op_type.strip():
            raise ValueError(f"PatchOp.op_type must be a non-empty string (got {self.op_type!r})")
        if self.op_type not in ("add_node", "add_edge", "update_claim_status"):
            raise ValueError(
                f"PatchOp.op_type must be add_node, add_edge, or update_claim_status "
                f"(got {self.op_type!r})"
            )
        if not isinstance(self.payload, dict) or not self.payload:
            raise ValueError(f"PatchOp.payload must be a non-empty dict (got {self.payload!r})")


@dataclass(frozen=True)
class GraphPatch:
    """A set of reversible operations applied to a TaskGraph.

    ``apply(graph)`` returns a NEW TaskGraph (immutability) with all
    operations applied sequentially. Each operation produces a new version.
    """

    operations: tuple[PatchOp, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.operations, tuple) or len(self.operations) == 0:
            raise ValueError(
                f"GraphPatch.operations must be a non-empty tuple (got {self.operations!r})"
            )

    def apply(self, graph: TaskGraph) -> TaskGraph:
        """Apply all operations sequentially; return the resulting graph."""
        result = graph
        for op in self.operations:
            result = _apply_op(result, op)
        return result


def _apply_op(graph: TaskGraph, op: PatchOp) -> TaskGraph:
    """Apply a single PatchOp to the graph, returning a new version."""
    if op.op_type == "add_node":
        node_id = TaskNodeId(op.payload["node_id"])
        kind = NodeKind(op.payload["kind"])
        text = op.payload.get("text", "")
        node = TaskNode(id=node_id, kind=kind, text=text)
        return graph.add_node(node)

    if op.op_type == "add_edge":
        source = TaskNodeId(op.payload["source"])
        target = TaskNodeId(op.payload["target"])
        kind = EdgeKind(op.payload["kind"])
        edge = TaskEdge(source=source, target=target, kind=kind)
        return graph.add_edge(edge)

    # update_claim_status is handled by the application layer (Claim.with_status);
    # the domain TaskGraph does not store claim-status inline, so this op is a
    # no-op at the graph level. The application repair loop applies it via
    # Claim.with_status separately and emits a bridge event.
    if op.op_type == "update_claim_status":
        return graph

    raise ValueError(f"Unknown PatchOp.op_type: {op.op_type!r}")


# ── Measurable improvement gate ──────────────────────────────────────────


def is_measurable_improvement(
    *,
    gaps_before: int,
    gaps_after: int,
    constraints_before: int,
    constraints_after: int,
    verified_before: int,
    verified_after: int,
) -> bool:
    """concept.md §7 measurable-improvement gate (pure function over counts).

    A patch is accepted if it improves the graph (gaps↓ OR verified_goals↑)
    WITHOUT worsening hard constraints. Specifically:

    Accept if:
      (gaps_after < gaps_before) OR (verified_after > verified_before)
    AND:
      constraints_after <= constraints_before

    A patch that does not improve (no change) is rejected — concept.md §7
    says repair must show measurable improvement, not just "not worse".
    """
    improved = (gaps_after < gaps_before) or (verified_after > verified_before)
    no_constraint_regression = constraints_after <= constraints_before
    return improved and no_constraint_regression
