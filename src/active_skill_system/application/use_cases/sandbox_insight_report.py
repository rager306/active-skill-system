"""L2 Application — Sandbox insight report (M049 S01).

Aggregates accumulated state from a GraphStore (LoopGraph + trajectory), a
RatchetLedger, and optionally a sandbox log directory into a single
InsightReport. Pure application layer (R002): no infrastructure imports
beyond ports.

Facts computed:
  1. total_loops          — count of loop vertices.
  2. total_vertices       — count of all vertices.
  3. total_edges          — count of all edges.
  4. runs_with_score_1    — loops whose last trajectory step was 'finish'.
  5. runs_with_score_lt_1 — loops whose last step was 'failure' or other.
  6. verifier_pass_rate   — runs_with_score_1 / total_loops.
  7. model_breakdown      — {model: count} derived from sandbox log files.
  8. trajectory_kinds     — {step_kind: count} across all trajectories.
  9. trajectory_lengths   — [int] per-loop step counts.
 10. executor_failures    — count of FAILURE-kind steps.
 11. skill_usage          — {skill: count} from USES edges to skill vertices.
 12. verifier_usage       — {verifier: count} from VERIFIED_BY edges.
 13. created_edges        — count (intent -> loop CREATED edges).
 14. ratchet_entries      — count of RatchetEntry rows.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class GraphReaderPort(Protocol):
    """Minimal read interface expected by ReportReader.

    LadybugGraphStore and InMemoryGraphStore both satisfy this.
    """

    def count_vertices(self) -> int: ...
    def count_edges(self) -> int: ...
    def get_vertex(self, vertex_id: str) -> Any: ...
    def query_neighbours(self, vertex_id: str, *, direction: str = "out") -> tuple[Any, ...]: ...
    def count_edges_by_kind(self, kind_value: str) -> int: ...
    def list_vertex_ids(self) -> tuple[str, ...]: ...


class RatchetLedgerPort(Protocol):
    """Minimal read interface for RatchetLedger."""

    @property
    def entries(self) -> list[Any]: ...


@dataclass(frozen=True)
class InsightReport:
    """Pure-data aggregation of accumulated sandbox state.

    All counts are zero-initialised; empty graph / missing ratchet yield a
    well-formed InsightReport with zero counts (NOT an error).
    """

    total_loops: int = 0
    total_vertices: int = 0
    total_edges: int = 0
    runs_with_score_1: int = 0
    runs_with_score_lt_1: int = 0
    verifier_pass_rate: float = 0.0
    model_breakdown: dict[str, int] = field(default_factory=dict)
    trajectory_kinds: dict[str, int] = field(default_factory=dict)
    trajectory_lengths: tuple[int, ...] = ()
    executor_failures: int = 0
    skill_usage: dict[str, int] = field(default_factory=dict)
    verifier_usage: dict[str, int] = field(default_factory=dict)
    created_edges: int = 0
    ratchet_entries: int = 0

    def facts(self) -> tuple[tuple[str, Any], ...]:
        """Ordered (label, value) pairs for human-readable output."""
        return (
            ("total_loops", self.total_loops),
            ("total_vertices", self.total_vertices),
            ("total_edges", self.total_edges),
            ("runs_with_score_1", self.runs_with_score_1),
            ("runs_with_score_lt_1", self.runs_with_score_lt_1),
            ("verifier_pass_rate", f"{self.verifier_pass_rate:.2%}"),
            ("model_breakdown", dict(self.model_breakdown)),
            ("trajectory_kinds", dict(self.trajectory_kinds)),
            ("trajectory_lengths", list(self.trajectory_lengths)),
            ("executor_failures", self.executor_failures),
            ("skill_usage", dict(self.skill_usage)),
            ("verifier_usage", dict(self.verifier_usage)),
            ("created_edges", self.created_edges),
            ("ratchet_entries", self.ratchet_entries),
        )


class ReportReader:
    """Aggregator: GraphStore + RatchetLedger -> InsightReport.

    Pure L2 application. Does not import ladybug, RatchetLedger (concrete),
    or any I/O. The composition layer wires real implementations.
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

    def read(self) -> InsightReport:
        """Aggregate facts from the graph and ratchet. Empty-safe."""
        total_vertices = self._graph.count_vertices()
        total_edges = self._graph.count_edges()

        # Enumerate all vertices once.
        all_ids = self._graph.list_vertex_ids()
        loop_ids = tuple(vid for vid in all_ids if vid.startswith("loop:"))
        total_loops = len(loop_ids)

        traj_kinds: Counter[str] = Counter()
        traj_lens: list[int] = []
        models: Counter[str] = Counter()
        executor_failures = 0
        runs_with_score_1 = 0
        runs_with_score_lt_1 = 0
        skill_usage: dict[str, int] = {}
        verifier_usage: dict[str, int] = {}

        for vid, vertex in self._vertices_with_ids(all_ids):
            kind_value = _kind_value(vertex)
            label = _label_of(vertex, vid)
            if kind_value == "skill":
                skill_usage[label] = skill_usage.get(label, 0) + 1
            elif kind_value == "verifier":
                verifier_usage[label] = verifier_usage.get(label, 0) + 1

        for loop_id in loop_ids:
            steps = self._trajectory_steps_for_loop(loop_id)
            traj_lens.append(len(steps))
            last_kind = ""
            for step in steps:
                kind = _label_of(step, "")
                traj_kinds[kind] += 1
                last_kind = kind
                if kind == "failure":
                    executor_failures += 1
            # Score heuristic: last step kind drives verdict.
            if last_kind == "finish":
                runs_with_score_1 += 1
            elif last_kind == "failure":
                runs_with_score_lt_1 += 1
            elif last_kind == "":
                pass  # no trajectory
            else:
                # last step was something else (verify etc.) — treat as fail
                runs_with_score_lt_1 += 1

        verifier_pass_rate = (
            runs_with_score_1 / total_loops if total_loops else 0.0
        )
        created_edges = self._graph.count_edges_by_kind("created")
        ratchet_entries = len(self._ratchet.entries) if self._ratchet else 0
        models.update(self._models_from_logs())

        return InsightReport(
            total_loops=total_loops,
            total_vertices=total_vertices,
            total_edges=total_edges,
            runs_with_score_1=runs_with_score_1,
            runs_with_score_lt_1=runs_with_score_lt_1,
            verifier_pass_rate=verifier_pass_rate,
            model_breakdown=dict(models),
            trajectory_kinds=dict(traj_kinds),
            trajectory_lengths=tuple(traj_lens),
            executor_failures=executor_failures,
            skill_usage=skill_usage,
            verifier_usage=verifier_usage,
            created_edges=created_edges,
            ratchet_entries=ratchet_entries,
        )

    # ── helpers ───────────────────────────────────────────────────────

    def _vertices_with_ids(self, ids: tuple[str, ...]) -> list[tuple[str, Any]]:
        out: list[tuple[str, Any]] = []
        for vid in ids:
            v = self._graph.get_vertex(vid)
            if v is not None:
                out.append((vid, v))
        return out

    def _trajectory_steps_for_loop(self, loop_id: str) -> tuple[Any, ...]:
        neighbours = self._graph.query_neighbours(loop_id, direction="out")
        steps = tuple(n for n in neighbours if _kind_value(n) == "trajectory_step")
        # Sort by id suffix (-NNN) so 'last_kind' reflects the final step.
        return tuple(sorted(steps, key=lambda s: getattr(s, "id", "")))

    def _models_from_logs(self) -> Counter[str]:
        """Parse session_start lines to count model usage.

        Line format from mini_sandbox:
          ... session_start model=<name> executor=...
        """
        out: Counter[str] = Counter()
        if self._log_dir is None or not self._log_dir.exists():
            return out
        pattern = re.compile(r"session_start\s+model=(\S+)")
        for log_path in sorted(self._log_dir.glob("*.log")):
            try:
                text = log_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                m = pattern.search(line)
                if m:
                    model = m.group(1)
                    if model and model != "None":
                        out[model] += 1
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
