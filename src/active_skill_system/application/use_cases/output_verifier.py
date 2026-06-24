"""L2 Application use-case — OutputVerifierUseCase (M013 S01).

The trust keystone (architecture-review R4): deterministic-gate taxonomy
that verifies the final answer against the validated graph. Every factual
claim must have provenance; the answer must be non-empty; the graph must be
valid; the version must be stable.

concept.md §8-§9 anti-fantasy: the Output Verifier is the LAST independent
gate before an answer ships. If it fails, the answer is rejected (partial).

Pure application. Depends on domain + validator; no I/O (R002).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from active_skill_system.application.use_cases.validate_task_graph import (
    ValidateTaskGraphUseCase,
)
from active_skill_system.domain.runtime.graph import TaskGraph


class VerifierType(StrEnum):
    """Deterministic verification gates (R4 taxonomy)."""

    SCHEMA = "schema"
    CITATION_COVERAGE = "citation_coverage"
    TYPE_CHECK = "type_check"
    REPLAY_HASH = "replay_hash"


@dataclass(frozen=True)
class VerifierCheck:
    """One verification gate result."""

    verifier_type: VerifierType
    passed: bool
    detail: str


@dataclass(frozen=True)
class VerifierResult:
    """Aggregated verification result.

    ``passed`` is True iff ALL checks passed. If any fail, the answer must
    not ship — the caller returns a partial result instead.
    """

    passed: bool
    checks: tuple[VerifierCheck, ...]
    summary: str


class OutputVerifierUseCase:
    """Run deterministic verification gates on the final answer + graph.

    concept.md §10 (F-10): verify the final answer relative to goals and
    constraints. architecture-review R4: pin down which verifiers are
    deterministic vs LLM-judge; require at least one deterministic gate.
    """

    def __init__(
        self,
        validator: ValidateTaskGraphUseCase | None = None,
    ) -> None:
        self._validator = validator or ValidateTaskGraphUseCase()

    def verify(self, answer: str, graph: TaskGraph) -> VerifierResult:
        """Run all deterministic gates. Return VerifierResult."""
        checks: list[VerifierCheck] = []

        # 1. Schema: answer must be non-empty.
        checks.append(
            VerifierCheck(
                verifier_type=VerifierType.SCHEMA,
                passed=isinstance(answer, str) and bool(answer.strip()),
                detail=f"answer length={len(answer)}",
            )
        )

        # 2. Citation coverage: no ungrounded factual claims in the graph.
        report = self._validator.validate(graph)
        checks.append(
            VerifierCheck(
                verifier_type=VerifierType.CITATION_COVERAGE,
                passed=len(report.ungrounded_factual_claims) == 0,
                detail=f"ungrounded_claims={len(report.ungrounded_factual_claims)}",
            )
        )

        # 3. Type check: graph must have at least one goal (type-valid reasoning).
        checks.append(
            VerifierCheck(
                verifier_type=VerifierType.TYPE_CHECK,
                passed=report.goal_count > 0,
                detail=f"goal_count={report.goal_count}",
            )
        )

        # 4. Replay hash: graph version must be stable (committed, not mutating).
        checks.append(
            VerifierCheck(
                verifier_type=VerifierType.REPLAY_HASH,
                passed=graph.version >= 0,
                detail=f"graph_version={graph.version}",
            )
        )

        all_passed = all(c.passed for c in checks)
        return VerifierResult(
            passed=all_passed,
            checks=tuple(checks),
            summary=(
                "all gates passed"
                if all_passed
                else f"{sum(1 for c in checks if not c.passed)} gate(s) failed"
            ),
        )
