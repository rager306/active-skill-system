"""L2 Application — SandboxRunDiff (M049 S02).

Compares two runs side-by-side: trajectory kind set, score, model, step count.
Pure application layer (R002). Reads GraphReaderPort + log_dir.

The output ``RunComparison`` is the source from which the composition layer
prints a human-readable diff or a JSON dump.

Usage::

    diff = SandboxRunDiff(graph=store, log_dir='logs/sandbox')
    cmp = diff.compare('sandbox-run-abc', 'sandbox-run-def')
    if cmp.missing_id:
        raise ValueError(f'run not found: {cmp.missing_id}')
    print(cmp.summary())
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class GraphReaderPort(Protocol):
    """Minimal read interface — same shape as ReportReader uses."""

    def get_vertex(self, vertex_id: str) -> Any: ...
    def query_neighbours(self, vertex_id: str, *, direction: str = "out") -> tuple[Any, ...]: ...
    def list_vertex_ids(self) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class RunSummary:
    """One run's snapshot used for comparison."""

    loop_id: str
    score: float  # 1.0 on finish, 0.0 on failure, 0.5 if unknown
    trajectory_kinds: dict[str, int] = field(default_factory=dict)
    trajectory_length: int = 0
    model: str | None = None


@dataclass(frozen=True)
class RunComparison:
    """Diff between two RunSummary snapshots.

    ``missing_id`` is non-empty when either loop could not be located.
    Other fields are populated only when both runs are present.
    """

    loop_a: RunSummary | None = None
    loop_b: RunSummary | None = None
    missing_id: str = ""
    kinds_only_in_a: tuple[str, ...] = ()
    kinds_only_in_b: tuple[str, ...] = ()
    kinds_in_both: tuple[str, ...] = ()
    score_delta: float = 0.0
    length_delta: int = 0
    models_match: bool | None = None

    def summary(self) -> str:
        """Human-readable one-paragraph diff."""
        if self.missing_id:
            return f"run not found: {self.missing_id}"
        if self.loop_a is None or self.loop_b is None:
            return "(incomplete comparison)"
        a, b = self.loop_a, self.loop_b
        lines = [
            f"compare: {a.loop_id} vs {b.loop_id}",
            f"  score:       {a.score:.2f}  vs  {b.score:.2f}  (delta {self.score_delta:+.2f})",
            f"  length:      {a.trajectory_length}  vs  {b.trajectory_length}  (delta {self.length_delta:+d})",
            f"  model:       {a.model or '?'}  vs  {b.model or '?'}  (match={self.models_match})",
            f"  only in A:   {sorted(self.kinds_only_in_a) or '(none)'}",
            f"  only in B:   {sorted(self.kinds_only_in_b) or '(none)'}",
            f"  both:        {sorted(self.kinds_in_both) or '(none)'}",
        ]
        return "\n".join(lines)


class SandboxRunDiff:
    """Compute side-by-side diff between two runs.

    Pure L2 application. Does not import LadybugGraphStore or RatchetLedger;
    composition wires the real implementations.
    """

    def __init__(
        self,
        graph: GraphReaderPort,
        log_dir: str | Path | None = None,
    ) -> None:
        if graph is None:
            raise TypeError("graph must be a GraphReaderPort")
        self._graph = graph
        self._log_dir = Path(log_dir) if log_dir else None

    def compare(self, loop_a_id: str, loop_b_id: str) -> RunComparison:
        """Build a RunComparison for the two given loop ids.

        Either loop id may be the bare id (``sandbox-run-abc``) or
        already-prefixed (``loop:sandbox-run-abc``).
        """
        norm_a = self._normalize(loop_a_id)
        norm_b = self._normalize(loop_b_id)

        if not self._exists(norm_a):
            return RunComparison(missing_id=norm_a)
        if not self._exists(norm_b):
            return RunComparison(missing_id=norm_b)

        sum_a = self._summary(norm_a)
        sum_b = self._summary(norm_b)
        if sum_a is None or sum_b is None:
            return RunComparison(missing_id=norm_a if sum_a is None else norm_b)

        set_a = set(sum_a.trajectory_kinds)
        set_b = set(sum_b.trajectory_kinds)
        return RunComparison(
            loop_a=sum_a,
            loop_b=sum_b,
            kinds_only_in_a=tuple(sorted(set_a - set_b)),
            kinds_only_in_b=tuple(sorted(set_b - set_a)),
            kinds_in_both=tuple(sorted(set_a & set_b)),
            score_delta=sum_b.score - sum_a.score,
            length_delta=sum_b.trajectory_length - sum_a.trajectory_length,
            models_match=(
                None if (sum_a.model is None or sum_b.model is None)
                else sum_a.model == sum_b.model
            ),
        )

    # ── helpers ───────────────────────────────────────────────────────

    def _normalize(self, loop_id: str) -> str:
        return loop_id if loop_id.startswith("loop:") else f"loop:{loop_id}"

    def _exists(self, loop_id: str) -> bool:
        return self._graph.get_vertex(loop_id) is not None

    def _summary(self, loop_id: str) -> RunSummary | None:
        if self._graph.get_vertex(loop_id) is None:
            return None
        steps = self._steps_for_loop(loop_id)
        kinds: Counter[str] = Counter()
        last_kind = ""
        for step in steps:
            kind = _label_of(step, "")
            kinds[kind] += 1
            last_kind = kind
        score = 1.0 if last_kind == "finish" else (0.0 if last_kind == "failure" else 0.5)
        bare_id = loop_id.removeprefix("loop:")
        model = self._model_for_run(bare_id)
        return RunSummary(
            loop_id=bare_id,
            score=score,
            trajectory_kinds=dict(kinds),
            trajectory_length=len(steps),
            model=model,
        )

    def _steps_for_loop(self, loop_id: str) -> tuple[Any, ...]:
        neighbours = self._graph.query_neighbours(loop_id, direction="out")
        steps = tuple(n for n in neighbours if _kind_value(n) == "trajectory_step")
        return tuple(sorted(steps, key=lambda s: getattr(s, "id", "")))

    def _model_for_run(self, run_id: str) -> str | None:
        """Find model for a given run id by parsing session_start lines.

        The line format is::
            ... session_start model=<name> executor=...
        The first session_start line containing ``run_id=<...>`` wins.
        Without that, falls back to the most-recent session_start before
        any ``run_complete run_id=<our_id>`` entry.
        """
        if self._log_dir is None or not self._log_dir.exists():
            return None
        pattern_start = re.compile(r"session_start\s+model=(\S+)")
        pattern_complete = re.compile(rf"run_complete\s+run_id={re.escape(run_id)}\b")
        last_start_model: str | None = None
        for log_path in sorted(self._log_dir.glob("*.log")):
            try:
                text = log_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                m_start = pattern_start.search(line)
                if m_start:
                    candidate = m_start.group(1)
                    if candidate and candidate != "None":
                        last_start_model = candidate
                if pattern_complete.search(line) and last_start_model:
                    return last_start_model
        return last_start_model


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
