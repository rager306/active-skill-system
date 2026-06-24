"""L1 Domain - Cognitive Runtime bounded context (Task Graph + Run FSM).

Pure domain. NO I/O, NO infrastructure imports (R002). Frozen dataclasses with
``__post_init__`` invariant validation. stdlib + typing only.

Entities (re-exported):

  TaskNode, NodeKind, TaskNodeId (nodes.py)
  TaskEdge, EdgeKind (edges.py)
  Claim, ClaimStatus, GroundingKind (claim.py)
  TaskGraph (graph.py)
  RunFSM, RunState (fsm.py)
  MediaRef, ALLOWED_MEDIA_TYPES (media_ref.py)
  GapClass, GapClassification, Severity (gap.py)
  GraphPatch, PatchOp, is_measurable_improvement (patch.py)
"""

from active_skill_system.domain.runtime.claim import (
    LEGITIMATE_GROUNDING,
    Claim,
    ClaimStatus,
    GroundingKind,
)
from active_skill_system.domain.runtime.edges import EdgeKind, TaskEdge
from active_skill_system.domain.runtime.fsm import (
    LEGAL_TRANSITIONS,
    TERMINAL_STATES,
    RunFSM,
    RunState,
    is_legal_transition,
)
from active_skill_system.domain.runtime.gap import (
    GapClass,
    GapClassification,
    Severity,
    severity_rank,
)
from active_skill_system.domain.runtime.graph import TaskGraph
from active_skill_system.domain.runtime.media_ref import (
    ALLOWED_MEDIA_TYPES,
    MediaRef,
)
from active_skill_system.domain.runtime.nodes import NodeKind, TaskNode, TaskNodeId
from active_skill_system.domain.runtime.patch import (
    GraphPatch,
    PatchOp,
    is_measurable_improvement,
)

__all__ = [
    "ALLOWED_MEDIA_TYPES",
    "GapClass",
    "GapClassification",
    "GraphPatch",
    "LEGAL_TRANSITIONS",
    "LEGITIMATE_GROUNDING",
    "Claim",
    "ClaimStatus",
    "EdgeKind",
    "GroundingKind",
    "MediaRef",
    "NodeKind",
    "PatchOp",
    "RunFSM",
    "RunState",
    "Severity",
    "TERMINAL_STATES",
    "TaskEdge",
    "TaskGraph",
    "TaskNode",
    "TaskNodeId",
    "is_legal_transition",
    "is_measurable_improvement",
    "severity_rank",
]
