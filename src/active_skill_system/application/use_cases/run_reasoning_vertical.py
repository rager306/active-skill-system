"""L2 Application use-case — first vertical slice of the Cognitive Runtime.

Deterministically turns a structured ``TaskSpec`` into a versioned ``TaskGraph``,
validates it with ``ValidateTaskGraphUseCase``, and returns a ``ReasoningResult``
that tells the caller whether the goal is answer-ready or blocked by gaps /
ungrounded claims (concept.md §5 supervisor, §8 anti-fantasy).

This is the first end-to-end seam of the Cognitive Runtime (M003 scope): no
LLM, no tools, no repair-loop — the input is structured and the answer is the
validated trajectory + explicit gaps. The load-bearing guarantee it proves:

> An ungrounded claim cannot reach ``answer_ready=True``; it surfaces as a gap
> instead. (concept.md §8, architecture.md §6.2)

Pure application. Depends on domain + the validator only; no I/O (R002/R004).
"""

from __future__ import annotations

from dataclasses import dataclass

from active_skill_system.application.use_cases.validate_task_graph import (
    ValidateTaskGraphUseCase,
)
from active_skill_system.domain.runtime import (
    EdgeKind,
    MediaRef,
    NodeKind,
    TaskEdge,
    TaskGraph,
    TaskNode,
    TaskNodeId,
)


@dataclass(frozen=True)
class ClaimSpec:
    """A claim to seed into the graph.

    If ``evidence_id`` is set, the builder adds an Evidence node + a DERIVED_FROM
    edge so the claim is grounded. If it is None, the claim ships ungrounded and
    the validator flags it as an anti-fantasy gap.
    """

    text: str
    evidence_id: str | None = None


@dataclass(frozen=True)
class TaskSpec:
    """Structured input to the vertical slice (no free text / LLM parsing yet).

    ``attachments`` is a tuple of ``MediaRef`` (M008): images (or future
    video) that the pipeline will use for vision extraction before the
    reasoning pass. Vision-extracted facts land in ``facts`` after the
    ParseTaskSpecUseCase runs.
    """

    goal: str
    facts: tuple[str, ...] = ()
    claims: tuple[ClaimSpec, ...] = ()
    attachments: tuple[MediaRef, ...] = ()


@dataclass(frozen=True)
class ReasoningResult:
    """Structured outcome of the vertical slice.

    - answer_ready: True iff the goal is reachable AND there are no ungrounded
      factual claims AND no constraint violations.
    - reachable, supported_goals, gaps, ungrounded_claims: projected from the
      ValidationReport.
    """

    answer_ready: bool
    reachable: bool
    supported_goals: tuple[str, ...]
    gaps: tuple[str, ...]
    ungrounded_claims: tuple[str, ...]


class RunReasoningVerticalUseCase:
    """Build a TaskGraph from a TaskSpec, validate it, return a ReasoningResult."""

    def __init__(self, validator: ValidateTaskGraphUseCase | None = None) -> None:
        self._validator = validator or ValidateTaskGraphUseCase()

    def run(self, task_spec: TaskSpec) -> ReasoningResult:
        graph = _build_graph(task_spec)
        report = self._validator.validate(graph)
        return ReasoningResult(
            answer_ready=(
                report.reachable
                and not report.ungrounded_factual_claims
                and not report.constraint_violations
            ),
            reachable=report.reachable,
            supported_goals=report.supported_goal_ids,
            gaps=tuple(g.node_id for g in report.gaps),
            ungrounded_claims=report.ungrounded_factual_claims,
        )


def _build_graph(spec: TaskSpec) -> TaskGraph:
    """Deterministically construct an initial versioned TaskGraph from a TaskSpec."""
    if not isinstance(spec.goal, str) or not spec.goal.strip():
        raise ValueError("TaskSpec.goal must be a non-empty string")

    graph = TaskGraph()
    goal_id = TaskNodeId("goal")
    # Goal node first: every support edge references it, so it must exist before edges.
    graph = graph.add_node(TaskNode(id=goal_id, kind=NodeKind.GOAL, text=spec.goal))

    # Facts seed grounded support directly under the goal.
    for i, fact_text in enumerate(spec.facts):
        fid = TaskNodeId(f"fact{i}")
        graph = graph.add_node(
            TaskNode(id=fid, kind=NodeKind.FACT, text=fact_text)
        ).add_edge(TaskEdge(source=fid, target=goal_id, kind=EdgeKind.SUPPORTS))

    # Claims: grounded if evidence_id given, else ungrounded (flagged by validator).
    for i, claim in enumerate(spec.claims):
        cid = TaskNodeId(f"claim{i}")
        graph = graph.add_node(
            TaskNode(id=cid, kind=NodeKind.CLAIM, text=claim.text)
        ).add_edge(TaskEdge(source=cid, target=goal_id, kind=EdgeKind.SUPPORTS))
        if claim.evidence_id is not None:
            eid = TaskNodeId(claim.evidence_id)
            # ensure the evidence node exists, then ground the claim via it
            if not graph.has(eid):
                graph = graph.add_node(
                    TaskNode(id=eid, kind=NodeKind.EVIDENCE, text="")
                )
            graph = graph.add_edge(
                TaskEdge(source=eid, target=cid, kind=EdgeKind.DERIVED_FROM)
            )

    # Attachments (M008): for each MediaRef in spec.attachments, ensure an
    # Evidence node exists with media=MediaRef. These act as grounding
    # anchors for any claim that has matching evidence_id. The validator
    # still treats these Evidence nodes as grounded (Fact/Evidence kinds are
    # inherently grounded by the validate_task_graph logic).
    for i, media in enumerate(spec.attachments):
        eid = TaskNodeId(f"attachment{i}")
        if not graph.has(eid):
            graph = graph.add_node(
                TaskNode(id=eid, kind=NodeKind.EVIDENCE, text="", media=media)
            )

    return graph.commit()
