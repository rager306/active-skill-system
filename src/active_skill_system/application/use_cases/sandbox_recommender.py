"""L2 Application — SandboxRecommender (M049 S03).

Rule-based recommender that turns accumulated data (graph + log_dir + ratchet)
into a list of typed ``Recommendation`` records. Each recommendation has a
``kind``, a ``message``, a ``confidence`` level, and a list of evidence refs.

Pure application layer (R002). Does not import LadybugGraphStore or
RatchetLedger; composition wires real implementations.

Recommendation kinds produced:
  - model_stable:        one model with 100% pass rate.
  - executor_gate_safe:  executor_gate never rejected.
  - undertested_model:   one model dominates; recommend more variety.
  - failed_run_present:  at least one failed run; suggest ratchet review.
  - trajectory_uniform:  all runs had identical step sequences.
  - trajectory_drift:    trajectory kinds varied across runs.
  - no_data:             empty graph (hint: run sandbox first).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class GraphReaderPort(Protocol):
    """Same shape ReportReader / SandboxRunDiff use."""

    def get_vertex(self, vertex_id: str) -> Any: ...
    def query_neighbours(self, vertex_id: str, *, direction: str = "out") -> tuple[Any, ...]: ...
    def list_vertex_ids(self) -> tuple[str, ...]: ...


class RatchetLedgerPort(Protocol):
    @property
    def entries(self) -> tuple[Any, ...]: ...


@dataclass(frozen=True)
class Recommendation:
    """One actionable insight."""

    kind: str
    message: str
    confidence: str = "low"
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "message": self.message,
            "confidence": self.confidence,
            "evidence_refs": list(self.evidence_refs),
        }


class SandboxRecommender:
    """Pure-L2 rule-based recommender.

    Inspects the accumulated graph (loops + trajectories), the ratchet, and
    the sandbox log directory. Returns a list of ``Recommendation`` records
    ordered by confidence (high first).
    """

    def __init__(
        self,
        graph: GraphReaderPort,
        ratchet: RatchetLedgerPort | None = None,
        log_dir: str | Path | None = None,
    ) -> None:
        if graph is None:
            raise TypeError("graph must be a GraphReaderPort")
        self._graph = graph
        self._ratchet = ratchet
        self._log_dir = Path(log_dir) if log_dir else None

    def recommend(self) -> tuple[Recommendation, ...]:
        out: list[Recommendation] = []

        all_ids = self._graph.list_vertex_ids()
        loop_ids = tuple(vid for vid in all_ids if vid.startswith("loop:"))
        if not loop_ids:
            return (Recommendation(
                kind="no_data",
                message="graph is empty — run sandbox first to populate knowledge",
                confidence="high",
            ),)

        scores: list[float] = []
        traj_kinds_per_loop: list[tuple[str, ...]] = []
        failure_count = 0
        for loop_id in loop_ids:
            steps = self._trajectory_steps_for_loop(loop_id)
            kinds = tuple(_label_of(s, "") for s in steps)
            traj_kinds_per_loop.append(kinds)
            last = kinds[-1] if kinds else ""
            if last == "finish":
                scores.append(1.0)
            elif last == "failure":
                scores.append(0.0)
                failure_count += 1
            else:
                scores.append(0.5)

        all_pass = all(s >= 1.0 for s in scores)
        all_fail = all(s < 1.0 for s in scores)
        models = self._models_from_logs()
        model_counts = Counter(models.values())
        dominant_model, dominant_count = (
            model_counts.most_common(1)[0] if model_counts else (None, 0)
        )

        # Rule 1: model_stable (all runs score 1.0 AND same model).
        if all_pass and len(model_counts) == 1 and dominant_model:
            out.append(Recommendation(
                kind="model_stable",
                message=f"model {dominant_model} has 100% pass rate across {len(loop_ids)} runs",
                confidence="high",
                evidence_refs=tuple(loop_ids),
            ))

        # Rule 2: executor_gate_safe (no FAILURE steps recorded).
        if failure_count == 0 and all_pass:
            out.append(Recommendation(
                kind="executor_gate_safe",
                message="no executor_gate failures across runs — gate is currently safety net only",
                confidence="medium",
                evidence_refs=tuple(loop_ids),
            ))

        # Rule 3: undertested_model (one model dominates).
        if len(loop_ids) >= 2 and dominant_count == len(loop_ids) and len(model_counts) == 1 and dominant_model:
            out.append(Recommendation(
                kind="undertested_model",
                message=f"only model {dominant_model} tested — recommend at least 2 more for diversity",
                confidence="medium",
                evidence_refs=(dominant_model,),
            ))

        # Rule 4: failed_run_present (any failure).
        if failure_count > 0:
            ratchet_n = len(self._ratchet.entries) if self._ratchet else 0
            out.append(Recommendation(
                kind="failed_run_present",
                message=f"{failure_count} failed run(s) — review ratchet ({ratchet_n} entries) for permanent fixes",
                confidence="high" if failure_count > 1 else "medium",
                evidence_refs=tuple(lid for lid, s in zip(loop_ids, scores) if s < 1.0),
            ))

        # Rule 5: trajectory_uniform / trajectory_drift.
        unique_trajs = {t for t in traj_kinds_per_loop}
        if len(unique_trajs) == 1:
            out.append(Recommendation(
                kind="trajectory_uniform",
                message=f"all {len(loop_ids)} runs follow identical trajectory ({len(unique_trajs.pop())} steps)",
                confidence="medium",
                evidence_refs=tuple(loop_ids),
            ))
        elif len(unique_trajs) >= 2:
            out.append(Recommendation(
                kind="trajectory_drift",
                message=f"{len(unique_trajs)} distinct trajectories across {len(loop_ids)} runs — review for stability",
                confidence="low",
            ))

        # Rule 6: all-fail signal.
        if all_fail:
            out.append(Recommendation(
                kind="all_fail",
                message=f"all {len(loop_ids)} runs failed — sandbox pipeline may be broken",
                confidence="high",
                evidence_refs=tuple(loop_ids),
            ))

        # Sort by confidence: high > medium > low.
        order = {"high": 0, "medium": 1, "low": 2}
        out.sort(key=lambda r: order.get(r.confidence, 3))
        return tuple(out)

    # ── helpers ───────────────────────────────────────────────────────

    def _trajectory_steps_for_loop(self, loop_id: str) -> tuple[Any, ...]:
        neighbours = self._graph.query_neighbours(loop_id, direction="out")
        steps = tuple(n for n in neighbours if _kind_value(n) == "trajectory_step")
        return tuple(sorted(steps, key=lambda s: getattr(s, "id", "")))

    def _models_from_logs(self) -> dict[str, str]:
        """Map run_id -> model name parsed from session_start/run_complete lines."""
        if self._log_dir is None or not self._log_dir.exists():
            return {}
        pattern_start = re.compile(r"session_start\s+model=(\S+)")
        pattern_complete = re.compile(r"run_complete\s+run_id=(\S+)")
        out: dict[str, str] = {}
        for log_path in sorted(self._log_dir.glob("*.log")):
            try:
                text = log_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            current_model: str | None = None
            for line in text.splitlines():
                m_start = pattern_start.search(line)
                if m_start:
                    candidate = m_start.group(1)
                    if candidate and candidate != "None":
                        current_model = candidate
                m_complete = pattern_complete.search(line)
                if m_complete and current_model:
                    out[m_complete.group(1)] = current_model
        return out


def _kind_value(vertex: Any) -> str:
    kind = getattr(vertex, "kind", None)
    if kind is None:
        return ""
    return getattr(kind, "value", str(kind))


def _label_of(vertex: Any, fallback: str) -> str:
    label = getattr(vertex, "label", None)
    if isinstance(label, str) and label:
        return label
    vid = getattr(vertex, "id", None)
    if isinstance(vid, str) and vid:
        return vid
    return fallback
