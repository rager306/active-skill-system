"""L1 Domain — typed errors (M040 S02).

Semantic exception hierarchy replacing ad-hoc ``ValueError``/``TypeError`` at
the boundaries where the system can fail in identifiable ways. Each error
carries optional structured context (``entity_id``, ``phase``, ``cause``) so a
boundary handler can log it without re-parsing strings.

Hierarchy: every typed error subclasses both ``Exception`` and ``ValueError``.
The ``ValueError`` base preserves backward compatibility with existing
``except ValueError`` sites during the migration; new code should catch the
specific typed error instead.

Pure domain. NO infrastructure imports (R002/R003). stdlib only.
"""

from __future__ import annotations

from typing import Any


class ActiveSkillError(ValueError):
    """Base for all typed active-skill-system domain errors.

    Subclasses ``ValueError`` for backward compatibility with pre-typed
    ``except ValueError`` sites. New code should catch the specific subclass.
    """

    def __init__(
        self,
        message: str,
        *,
        entity_id: str | None = None,
        phase: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.entity_id = entity_id
        self.phase = phase
        self.cause = cause
        ctx: list[str] = []
        if entity_id is not None:
            ctx.append(f"entity_id={entity_id!r}")
        if phase is not None:
            ctx.append(f"phase={phase!r}")
        full = f"{message} ({', '.join(ctx)})" if ctx else message
        super().__init__(full)
        # Keep the raw message accessible for structured logging.
        self.message = message

    def context(self) -> dict[str, Any]:
        """Return structured context for logging (never includes secrets)."""
        return {
            "entity_id": self.entity_id,
            "phase": self.phase,
            "cause_type": type(self.cause).__name__ if self.cause else None,
        }


class ToolError(ActiveSkillError):
    """A tool invocation could not produce a result (compute/read/write failed)."""


class LLMUnavailable(ActiveSkillError):
    """No provider could serve the request (all retries/fallbacks exhausted)."""


class BudgetExhausted(ActiveSkillError):
    """A run/loop exceeded its budget (calls, cost, iterations, or deadline)."""


class ContextLimitExceeded(ActiveSkillError):
    """Assembled context exceeded the model's context window."""


class EvolutionConverged(ActiveSkillError):
    """Evolution cannot make further progress (no improving mutation available)."""
