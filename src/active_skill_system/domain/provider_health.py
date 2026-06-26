"""L1 Domain — ProviderHealth value object (M038 S01).

Tracks the health of an LLM provider so the routing layer can skip degraded
providers and fall back through a chain. Immutable: every transition returns a
new instance (record_failure / record_success).

Pure domain. NO I/O, NO infrastructure imports (R002). stdlib only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderHealth:
    """Health state of a single LLM provider.

    Carries:
      - provider_id: unique provider identifier (e.g. "router", "fallback").
      - consecutive_failures: number of failures in a row (int, >= 0).
      - last_error: the most recent error message (str or None).
      - last_success_at: epoch seconds of the last success (float or None).
    """

    provider_id: str
    consecutive_failures: int = 0
    last_error: str | None = None
    last_success_at: float | None = None

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.provider_id, str) or not self.provider_id.strip():
            errors.append(f"provider_id must be a non-empty string (got {self.provider_id!r})")
        if not isinstance(self.consecutive_failures, int) or isinstance(
            self.consecutive_failures, bool
        ) or self.consecutive_failures < 0:
            errors.append(
                f"consecutive_failures must be a non-negative int (got {self.consecutive_failures!r})"
            )
        if self.last_error is not None and (
            not isinstance(self.last_error, str) or not self.last_error.strip()
        ):
            errors.append(f"last_error must be a non-empty string or None (got {self.last_error!r})")
        if self.last_success_at is not None and (
            not isinstance(self.last_success_at, (int, float))
            or isinstance(self.last_success_at, bool)
            or float(self.last_success_at) < 0.0
        ):
            errors.append(
                f"last_success_at must be a non-negative number or None (got {self.last_success_at!r})"
            )
        if errors:
            raise ValueError("ProviderHealth invariant violation: " + "; ".join(errors))

    def record_failure(self, error: str) -> ProviderHealth:
        """Return a new ProviderHealth with one more consecutive failure."""
        if not isinstance(error, str) or not error.strip():
            raise ValueError(f"error must be a non-empty string (got {error!r})")
        return ProviderHealth(
            provider_id=self.provider_id,
            consecutive_failures=self.consecutive_failures + 1,
            last_error=error,
            last_success_at=self.last_success_at,
        )

    def record_success(self, *, now: float | None = None) -> ProviderHealth:
        """Return a new ProviderHealth with failures reset and success timestamped."""
        ts = float(now) if now is not None else time.monotonic()
        return ProviderHealth(
            provider_id=self.provider_id,
            consecutive_failures=0,
            last_error=None,
            last_success_at=ts,
        )

    def is_healthy(self, *, max_failures: int = 3) -> bool:
        """True when consecutive_failures is below the degradation threshold."""
        if not isinstance(max_failures, int) or max_failures < 1:
            raise ValueError(f"max_failures must be a positive int (got {max_failures!r})")
        return self.consecutive_failures < max_failures
