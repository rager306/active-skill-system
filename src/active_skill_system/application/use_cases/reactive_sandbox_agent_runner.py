"""L2 Application — ReactiveSandboxAgentRunner (M054 S07).

Wraps SandboxAgentRunner to publish trajectory events to a BehaviorRuntime.
This is the REAL integration: reactive behaviors fire during actual LLM
agent runs, not just in demo mode.

The wrapper publishes lifecycle events (run.started, claim.created,
verify.completed, etc.) to the BehaviorRuntime. Registered behaviors react
automatically. This transforms the sandbox from a static pipeline into a
reactive system.

The wrapper is NON-DESTRUCTIVE: it doesn't modify the existing
SandboxAgentRunner. It wraps it and adds reactive event publishing on top.
Existing tests + callers are unaffected.

Usage:
    runner = SandboxAgentRunner(engine=strategy, sandbox_dir=tmp)
    reactive = ReactiveSandboxAgentRunner(
        runner=runner,
        behavior_runtime=runtime,
        event_store=store,  # optional audit trail
    )
    result = reactive.run(model="minimax/MiniMax-M3")
"""

from __future__ import annotations

import logging
from typing import Any

from active_skill_system.application.ports.behavior_runtime import BehaviorRuntime
from active_skill_system.application.ports.event_store import EventStore
from active_skill_system.application.use_cases.sandbox_agent_runner import (
    SandboxAgentRunner,
    SandboxRunResult,
)
from active_skill_system.domain.graph_primitives import GraphEvent

logger = logging.getLogger(__name__)


class ReactiveSandboxAgentRunner:
    """Wraps SandboxAgentRunner with reactive event publishing.

    Publishes lifecycle events to BehaviorRuntime (behaviors fire automatically)
    and optionally to EventStore (audit trail). This is the integration that
    makes the reactive system work during REAL agent runs.

    Args:
        runner: the underlying SandboxAgentRunner to wrap.
        behavior_runtime: where to publish events (behaviors react).
        event_store: optional EventStore for audit trail persistence.
        reactive_frame: optional ReactiveFrame for budget + behavior scoping.
    """

    def __init__(
        self,
        *,
        runner: SandboxAgentRunner,
        behavior_runtime: BehaviorRuntime,
        event_store: EventStore | None = None,
        reactive_frame: Any = None,
    ) -> None:
        if runner is None:
            raise TypeError("runner must be a non-None SandboxAgentRunner")
        if behavior_runtime is None:
            raise TypeError("behavior_runtime must be a non-None BehaviorRuntime")
        self._runner = runner
        self._runtime = behavior_runtime
        self._store = event_store
        self._frame = reactive_frame

    def run(
        self,
        *,
        model: str | None = None,
        max_tokens: int = 524_288,
        temperature: float = 0.0,
        timeout_seconds: float = 120.0,
    ) -> SandboxRunResult:
        """Run the sandbox agent with reactive event publishing.

        Delegates to the underlying SandboxAgentRunner.run(), but publishes
        lifecycle events before/after each phase. Behaviors react to these
        events automatically.
        """
        resolved_model = model or "minimax/MiniMax-M3"

        # ── Phase 1: run.started ──────────────────────────────────────────
        self._publish("run.started", {
            "model": resolved_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }, run_id=f"reactive-{resolved_model}")

        # Check frame budget before proceeding.
        if self._frame is not None and self._frame.budget.is_exhausted:
            self._publish("frame.exhausted", {
                "exhausted_by": self._frame.budget.exhausted_by,
            }, run_id=f"reactive-{resolved_model}")
            # Return a minimal failed result (can't run with exhausted budget).
            return SandboxRunResult(
                loop=self._runner._engine,  # type: ignore[arg-type]
                fitness=type("F", (), {"score": 0.0, "passed": False, "details": "budget exhausted"})(),
                model=resolved_model,
                error="frame budget exhausted before run",
            )

        # ── Phase 2: delegate to underlying runner ────────────────────────
        try:
            result = self._runner.run(
                model=resolved_model,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
            )
        except Exception as e:  # noqa: BLE001
            self._publish("run.failed", {
                "model": resolved_model,
                "error": str(e),
            }, run_id=f"reactive-{resolved_model}")
            raise

        # Record LLM call in frame budget.
        if self._frame is not None:
            self._frame.budget.record_llm_call()

        # ── Phase 3: publish result events ────────────────────────────────
        self._publish("verify.completed", {
            "model": resolved_model,
            "score": result.fitness.score,
            "passed": result.fitness.score >= 1.0,
        }, run_id=result.loop.id)

        if result.fitness.score >= 1.0:
            self._publish("run.succeeded", {
                "model": resolved_model,
                "score": result.fitness.score,
            }, run_id=result.loop.id)
        else:
            self._publish("run.failed_verification", {
                "model": resolved_model,
                "score": result.fitness.score,
                "error": result.error or "verification failed",
            }, run_id=result.loop.id)

        # ── Phase 4: publish trajectory as claim.created events ───────────
        # Each trajectory step becomes a reactive event that behaviors can
        # react to (e.g. evidence_check fires on claim creation).
        for i, step in enumerate(result.trajectory):
            self._publish(f"trajectory.{step.kind}", {
                "step_index": i,
                "model": resolved_model,
                "kind": step.kind,
            }, run_id=result.loop.id)

        return result

    def _publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        run_id: str = "",
    ) -> None:
        """Publish an event to BehaviorRuntime + EventStore.

        Behaviors fire automatically. EventStore persists for audit trail.
        """
        event = GraphEvent(
            id=f"{event_type}.{run_id}.{self._runner._counter}",
            type=event_type,
            payload=payload,
            actor="reactive_runner",
            run_id=run_id,
            timestamp_ns=self._runner._counter,
        )

        # Publish to behavior runtime (behaviors fire).
        try:
            self._runtime.publish(event)
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to publish event %s to runtime: %s", event_type, e)

        # Persist to event store (audit trail).
        if self._store is not None:
            try:
                self._store.append(event)
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to persist event %s to store: %s", event_type, e)
