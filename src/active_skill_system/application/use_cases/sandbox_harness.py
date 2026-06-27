"""L2 Application — Sandbox multi-model harness (M042 S03, D013 mini-loop).

Runs the same feature-slice benchmark across N models, collects comparable
fitness per model, stores each run as a Loop+LoopGraph, and answers the reader
query: "which model produced the cleanest feature-slice?". This closes the
D013 mini-loop: objective multi-model fitness + LoopGraph provenance + a real
reader query that justifies the graph.

Pure application (R002): depends on the S02 SandboxAgentRunner + domain
Loop/LoopGraph. The provider is injected (REQUIRED). Per-model failures are
recorded as FAILED entries and do NOT abort the whole run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from active_skill_system.application.use_cases.sandbox_agent_runner import (
    SandboxAgentRunner,
    SandboxRunResult,
)

_log = logging.getLogger("active_skill_system.application.sandbox_harness")


@dataclass(frozen=True)
class ComparativeRunEntry:
    """One model's result in a comparative run."""

    model: str
    fitness_score: float
    loop_id: str
    loop_state: str
    error: str | None = None


@dataclass(frozen=True)
class ComparativeReport:
    """Aggregated result of a multi-model benchmark run.

    Carries per-model entries, the winner, and the reader-query answer.
    """

    entries: tuple[ComparativeRunEntry, ...] = ()
    winner_model: str | None = None
    winner_score: float = 0.0
    reader_query_answer: str = ""

    def table(self) -> str:
        """Render a human-readable comparative table."""
        lines = ["model | score | loop_state | error"]
        lines.append("------|-------|------------|------")
        for e in self.entries:
            lines.append(f"{e.model} | {e.fitness_score:.2f} | {e.loop_state} | {e.error or '-'}")
        lines.append(f"winner: {self.winner_model} ({self.winner_score:.2f})")
        lines.append(f"reader query: {self.reader_query_answer}")
        return "\n".join(lines)


class SandboxHarness:
    """Run the benchmark across multiple models; produce a ComparativeReport.

    Usage::

        harness = SandboxHarness(provider=my_provider, models=["a","b"])
        report = harness.run_all()
        print(report.table())
    """

    def __init__(
        self,
        *,
        engine: Any,
        models: list[str],
        sandbox_dir: str = "runs/sandbox",
    ) -> None:
        if engine is None:
            raise TypeError("engine must be a non-None ReasoningEnginePort")
        if not isinstance(models, list) or not models:
            raise ValueError("models must be a non-empty list")
        self._engine = engine
        self._models = list(models)
        self._sandbox_dir = sandbox_dir

    def run_all(self) -> ComparativeReport:
        """Run every model; collect results; determine winner + reader answer."""
        runner = SandboxAgentRunner(engine=self._engine, sandbox_dir=self._sandbox_dir)
        results: list[SandboxRunResult] = []
        for model in self._models:
            try:
                result = runner.run(model=model)
            except Exception as e:  # noqa: BLE001 — never abort the whole run
                _log.warning("harness: model %s aborted: %s", model, e)
                continue
            results.append(result)
        return self._build_report(results)

    def _build_report(self, results: list[SandboxRunResult]) -> ComparativeReport:
        entries: list[ComparativeRunEntry] = []
        for r in results:
            entries.append(
                ComparativeRunEntry(
                    model=r.model,
                    fitness_score=r.fitness.score,
                    loop_id=r.loop.id,
                    loop_state=r.loop.state.value,
                    error=r.error,
                )
            )
        winner = self._pick_winner(results)
        answer = self._reader_query(results, winner)
        return ComparativeReport(
            entries=tuple(entries),
            winner_model=winner.model if winner else None,
            winner_score=winner.fitness.score if winner else 0.0,
            reader_query_answer=answer,
        )

    @staticmethod
    def _pick_winner(results: list[SandboxRunResult]) -> SandboxRunResult | None:
        if not results:
            return None
        # Highest score wins; tie-break by lowest loc, then alphabetical model.
        return min(
            results,
            key=lambda r: (-r.fitness.score, r.fitness.loc, r.model),
        )

    @staticmethod
    def _reader_query(results: list[SandboxRunResult], winner: SandboxRunResult | None) -> str:
        """Answer: 'which model produced the cleanest slice?'"""
        if not results:
            return "no runs completed"
        if winner is None:
            return "no winner (all failed)"
        perfect = [r for r in results if r.fitness.score == 1.0]
        if perfect:
            names = ", ".join(sorted(r.model for r in perfect))
            return f"cleanest (score 1.0): {names}"
        return (
            f"best: {winner.model} (score {winner.fitness.score:.2f}, "
            f"loc {winner.fitness.loc}); {len(perfect)} models scored full marks"
        )
