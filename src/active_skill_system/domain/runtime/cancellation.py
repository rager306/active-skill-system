"""L1 Domain - Cancellation and Idempotency value-objects (M014 S01, F-13).

RunCancellation: records why and when a run was cancelled.
IdempotencyKey: a stable key for deduplicating identical requests.

Pure domain. NO I/O, NO infrastructure imports (R002). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class RunCancellation:
    """Records the cancellation of a run.

    Carries:
      - run_id: the id of the cancelled run.
      - reason: why it was cancelled (human-readable).
      - cancelled_at: UTC timestamp.
    """

    run_id: str
    reason: str
    cancelled_at: datetime = datetime.now(UTC)  # noqa: RUF009 — frozen dataclass field

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            errors.append(f"run_id must be a non-empty string (got {self.run_id!r})")
        if not isinstance(self.reason, str) or not self.reason.strip():
            errors.append(f"reason must be a non-empty string (got {self.reason!r})")
        if errors:
            raise ValueError("RunCancellation invariant violation: " + "; ".join(errors))


@dataclass(frozen=True)
class IdempotencyKey:
    """A stable key for deduplicating identical requests.

    Two RunGoal requests with the same IdempotencyKey should produce the
    same RunResult — the second request returns the cached result without
    re-executing the run.
    """

    key: str

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError(f"IdempotencyKey.key must be a non-empty string (got {self.key!r})")

    def __str__(self) -> str:
        return self.key
