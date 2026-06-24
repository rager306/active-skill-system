"""L2 Application use-case — validate a Task Graph (Cognitive Runtime).

Deterministic, pure validation of a ``TaskGraph`` against the reasoning rules
(concept.md §6 reachability, §7 gaps, §8 anti-fantasy):

  * **Reachability** — a Goal is reachable iff there is a support path
    (SUPPORTS / DERIVED_FROM / SATISFIES) from a grounded node (Fact / Evidence)
    to it. Grounded support propagates transitively.
  * **Gaps** — unsupported Goals + explicit Gap nodes.
  * **Constraint violations** — CONTRADICTS edges between nodes.
  * **Anti-fantasy gate** — a CLAIM node is a *factual* assertion; it counts as
    grounded only if it has a support path from Fact/Evidence. An ungrounded
    CLAIM that is not re-typed as HYPOTHESIS is an *ungrounded factual claim*
    violation (concept.md §8/§9 — a hypothesis is a formulation, not a fact,
    so it may ship without grounding).

This is the graph-level mirror of the Claim-level anti-fantasy invariant in
``domain/runtime/claim.py`` (which blocks an ungrounded VERIFIED Claim). Both
layers of defense hold independently.

Pure application. Depends on domain only; no I/O (R002/R004).
"""

from __future__ import annotations

from dataclasses import dataclass

from active_skill_system.domain.runtime import (
    EdgeKind,
    NodeKind,
    TaskGraph,
)

# Edge kinds that count as "support" for reachability.
_SUPPORT_EDGES = frozenset({EdgeKind.SUPPORTS, EdgeKind.DERIVED_FROM, EdgeKind.SATISFIES})

# Node kinds that are inherently grounded (need no further support).
_GROUNDED_KINDS = frozenset({NodeKind.FACT, NodeKind.EVIDENCE})

# Node kinds that are formulations, not factual assertions (may ship without
# grounding — anti-fantasy rule 4/5).
_NON_FACTUAL_KINDS = frozenset({NodeKind.HYPOTHESIS, NodeKind.GOAL, NodeKind.GAP})


@dataclass(frozen=True)
class Gap:
    """A detected gap: a node id + a human-readable reason."""

    node_id: str
    reason: str


@dataclass(frozen=True)
class ValidationReport:
    """The result of validating a TaskGraph.

    Carries:
      - reachable: True iff EVERY Goal node has grounded support.
      - goal_count: number of Goal nodes considered.
      - supported_goal_ids: Goals that have grounded support.
      - gaps: unsupported Goals + explicit Gap nodes.
      - constraint_violations: CONTRADICTS edges (each as "src->target").
      - ungrounded_factual_claims: CLAIM nodes lacking grounded support
        (the anti-fantasy gate at graph level).
    """

    reachable: bool
    goal_count: int = 0
    supported_goal_ids: tuple[str, ...] = ()
    gaps: tuple[Gap, ...] = ()
    constraint_violations: tuple[str, ...] = ()
    ungrounded_factual_claims: tuple[str, ...] = ()


class ValidateTaskGraphUseCase:
    """Validate a TaskGraph deterministically (concept.md §6-§9)."""

    def validate(self, graph: TaskGraph) -> ValidationReport:
        """Run all checks and return a ValidationReport."""
        nodes_by_id = {n.id: n for n in graph.nodes}

        support_sources: dict = {}
        for edge in graph.edges:
            if edge.kind in _SUPPORT_EDGES:
                support_sources.setdefault(edge.target, set()).add(edge.source)

        grounded = _propagate_grounded_support(graph, nodes_by_id, support_sources)

        goals = [n for n in graph.nodes if n.kind is NodeKind.GOAL]
        supported_goal_ids = tuple(
            sorted(str(g.id) for g in goals if _goal_supported(g.id, support_sources, grounded))
        )

        # Gaps: unsupported goals + explicit Gap nodes.
        gap_nodes: list[Gap] = [
            Gap(node_id=str(n.id), reason="explicit gap node") for n in graph.nodes if n.kind is NodeKind.GAP
        ]
        gap_nodes += [
            Gap(node_id=str(g.id), reason="goal has no grounded support path")
            for g in goals
            if not _goal_supported(g.id, support_sources, grounded)
        ]

        # Constraint violations: any CONTRADICTS edge.
        constraint_violations = tuple(
            f"{e.source}->{e.target}" for e in graph.edges if e.kind is EdgeKind.CONTRADICTS
        )

        # Anti-fantasy: CLAIM nodes that are not grounded and not re-typed as
        # hypothesis/formation are ungrounded factual claims.
        ungrounded_claims = tuple(
            sorted(
                str(n.id)
                for n in graph.nodes
                if n.kind is NodeKind.CLAIM and n.id not in grounded
            )
        )

        reachable = (
            len(goals) > 0
            and all(_goal_supported(g.id, support_sources, grounded) for g in goals)
        )

        return ValidationReport(
            reachable=reachable,
            goal_count=len(goals),
            supported_goal_ids=supported_goal_ids,
            gaps=tuple(gap_nodes),
            constraint_violations=constraint_violations,
            ungrounded_factual_claims=ungrounded_claims,
        )


def _goal_supported(
    goal_id, support_sources: dict, grounded: set
) -> bool:
    """True iff ``goal_id`` has a support path (recursively backward) to a grounded node.

    A Goal is supported when at least one of its support sources is itself
    grounded, or supported transitively. Visited guards against cycles.
    """
    stack = [goal_id]
    visited: set = set()
    while stack:
        cur = stack.pop()
        if cur in visited:
            continue
        visited.add(cur)
        for src in support_sources.get(cur, set()):
            if src in grounded:
                return True
            stack.append(src)
    return False


def _propagate_grounded_support(
    graph: TaskGraph, nodes_by_id: dict, support_sources: dict
) -> set:
    """Return the set of node ids that are grounded (transitively supported).

    A node is grounded if:
      - its kind is inherently grounded (Fact/Evidence), OR
      - it has an incoming support edge from an already-grounded node.

    HYPOTHESIS/GOAL/GAP nodes are never grounded as facts (they may be
    formulations, not assertions). This is a fixpoint computation.
    """
    grounded: set = set()
    # Seed with inherently grounded nodes.
    for n in graph.nodes:
        if n.kind in _GROUNDED_KINDS:
            grounded.add(n.id)

    # Fixpoint: a CLAIM node becomes grounded if a support source is grounded.
    changed = True
    while changed:
        changed = False
        for n in graph.nodes:
            if n.id in grounded:
                continue
            if n.kind is not NodeKind.CLAIM:
                continue  # only CLAIM nodes can gain factual grounding via support
            sources = support_sources.get(n.id, set())
            if any(s in grounded for s in sources):
                grounded.add(n.id)
                changed = True
    return grounded
