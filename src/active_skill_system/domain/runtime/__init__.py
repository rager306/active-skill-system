"""L1 Domain - Cognitive Runtime bounded context (Task Graph + Run FSM).

Pure domain. NO I/O, NO infrastructure imports (R002). Frozen dataclasses with
``__post_init__`` invariant validation. stdlib + typing only.

Entities (re-exported):

  TaskNode, NodeKind, TaskNodeId (nodes.py)
    Typed reasoning-graph nodes: Goal/Fact/Evidence/Constraint/Hypothesis/
    Gap/Mechanism/Claim/Decision/Action/Result.

  TaskEdge, EdgeKind (edges.py)
    Typed relations: SUPPORTS/REQUIRES/DERIVED_FROM/CONTRADICTS/BLOCKS/
    SATISFIES/REFINES/DEPENDS_ON/PRODUCES/INVALIDATES.

  Claim, ClaimStatus, GroundingKind (claim.py)
    Factual assertions with a lifecycle. Anti-fantasy invariant: a Claim
    cannot be promoted to VERIFIED without independent grounding (evidence
    OR a legitimate grounding kind).

  TaskGraph (graph.py)
    Immutable, versioned reasoning graph (monotone versioning + parent linkage).
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
from active_skill_system.domain.runtime.graph import TaskGraph
from active_skill_system.domain.runtime.media_ref import (
    ALLOWED_MEDIA_TYPES,
    MediaRef,
)
from active_skill_system.domain.runtime.nodes import NodeKind, TaskNode, TaskNodeId

__all__ = [
    "ALLOWED_MEDIA_TYPES",
    "LEGAL_TRANSITIONS",
    "LEGITIMATE_GROUNDING",
    "Claim",
    "ClaimStatus",
    "EdgeKind",
    "GroundingKind",
    "MediaRef",
    "NodeKind",
    "RunFSM",
    "RunState",
    "TERMINAL_STATES",
    "TaskEdge",
    "TaskGraph",
    "TaskNode",
    "TaskNodeId",
    "is_legal_transition",
]
