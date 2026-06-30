"""L1 Domain — ReactiveFrame (M054 S06, Wave D primitive #7).

A ReactiveFrame defines WHICH behaviors and policies are active for a run,
bounded by a budget. It connects the existing Loop budget model to the
reactive runtime (M053).

Mirrors activegraph Frame(goal, budget, behaviors): a bounded context that
scopes which reactive behaviors fire and enforces resource limits.

Pure domain. NO I/O, NO infrastructure imports (R002/R003). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FrameBudget:
    """Mutable budget tracker for a ReactiveFrame.

    Tracks usage of LLM calls, behavior firings, and patch proposals.
    When any limit is exceeded, the frame is exhausted and behaviors stop.

    Fields:
      - max_llm_calls: max LLM calls allowed (None = unlimited).
      - max_behavior_firings: max behavior handler firings (None = unlimited).
      - max_patch_proposals: max patches behaviors can propose (None = unlimited).
      - llm_calls_used: current LLM call count.
      - behavior_firings_used: current behavior firing count.
      - patch_proposals_used: current patch proposal count.
    """

    max_llm_calls: int | None = None
    max_behavior_firings: int | None = None
    max_patch_proposals: int | None = None
    llm_calls_used: int = 0
    behavior_firings_used: int = 0
    patch_proposals_used: int = 0

    @property
    def is_exhausted(self) -> bool:
        """True if any budget limit has been reached."""
        if self.max_llm_calls is not None and self.llm_calls_used >= self.max_llm_calls:
            return True
        if self.max_behavior_firings is not None and self.behavior_firings_used >= self.max_behavior_firings:
            return True
        if self.max_patch_proposals is not None:
            return self.patch_proposals_used >= self.max_patch_proposals
        return False

    @property
    def exhausted_by(self) -> str:
        """Which budget limit caused exhaustion (empty if not exhausted)."""
        if self.max_llm_calls is not None and self.llm_calls_used >= self.max_llm_calls:
            return "llm_calls"
        if self.max_behavior_firings is not None and self.behavior_firings_used >= self.max_behavior_firings:
            return "behavior_firings"
        if self.max_patch_proposals is not None and self.patch_proposals_used >= self.max_patch_proposals:
            return "patch_proposals"
        return ""

    def record_llm_call(self) -> None:
        """Record one LLM call."""
        self.llm_calls_used += 1

    def record_behavior_firing(self) -> None:
        """Record one behavior firing."""
        self.behavior_firings_used += 1

    def record_patch_proposal(self) -> None:
        """Record one patch proposal."""
        self.patch_proposals_used += 1


@dataclass(frozen=True)
class ReactiveFrame:
    """A bounded context that scopes reactive behaviors + policies.

    Fields:
      - goal: what this frame is trying to achieve (human-readable).
      - budget: FrameBudget with resource limits.
      - behavior_names: tuple of behavior names that are ACTIVE in this frame.
        Behaviors not in this list don't fire (even if registered).
      - policy_names: tuple of policy names that are ACTIVE in this frame.
      - metadata: optional additional frame attributes.

    A ReactiveFrame is the reactive equivalent of a Loop: it defines the
    scope of reactive activity for a run. Behaviors outside the frame are
    inactive. Budget exhaustion stops all reactive behavior.
    """

    goal: str
    budget: FrameBudget = field(default_factory=FrameBudget)
    behavior_names: tuple[str, ...] = ()
    policy_names: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.goal, str) or not self.goal.strip():
            errors.append(f"goal must be non-empty string (got {self.goal!r})")
        if not isinstance(self.budget, FrameBudget):
            errors.append(f"budget must be a FrameBudget (got {type(self.budget).__name__})")
        if not isinstance(self.behavior_names, tuple):
            errors.append(f"behavior_names must be a tuple (got {type(self.behavior_names).__name__})")
        if not isinstance(self.policy_names, tuple):
            errors.append(f"policy_names must be a tuple (got {type(self.policy_names).__name__})")
        if errors:
            raise ValueError("ReactiveFrame invariant violation: " + "; ".join(errors))

    def is_behavior_active(self, behavior_name: str) -> bool:
        """Check if a behavior is active within this frame.

        If behavior_names is empty, ALL behaviors are active (no scoping).
        Otherwise, only behaviors in the list are active.
        Budget exhaustion makes ALL behaviors inactive.
        """
        if self.budget.is_exhausted:
            return False
        if not self.behavior_names:
            return True  # empty = all active
        return behavior_name in self.behavior_names

    def is_policy_active(self, policy_name: str) -> bool:
        """Check if a policy is active within this frame."""
        if not self.policy_names:
            return True
        return policy_name in self.policy_names
