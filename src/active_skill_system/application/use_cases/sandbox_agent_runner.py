"""L2 Application — Sandbox agent runner (M042 S02 T01, D013 mini-loop).

The first real-LLM coding task inside the framework's own loop. Given the cache
benchmark spec (domain/sandbox_cache_task.py), it prompts ONE model to generate
a candidate ``cache_types`` module, extracts the Python code from the response,
writes it to a sandbox directory, runs the deterministic verifier (S01), and
records the run as a ``Loop`` (D009) with lifecycle events.

Pure application: depends on ``LLMProviderPort`` (injected, REQUIRED — no
adapter import, R002) and the domain Loop/verifier. The composition layer wires
the real provider (S02 T03).

LLM errors are caught and recorded as a Loop FAILED event with a typed error
(M040) — the run degrades gracefully, never leaking provider exceptions.
"""

from __future__ import annotations

import logging
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

from active_skill_system.application.ports.llm import LLMMessage, LLMProviderPort
from active_skill_system.application.use_cases.sandbox_verifier import (
    SandboxFitness,
    verify_candidate,
)
from active_skill_system.domain.loop import Budget, Loop, LoopEvent, LoopEventKind, LoopState
from active_skill_system.domain.sandbox_cache_task import REQUIRED_FIELDS

_log = logging.getLogger("active_skill_system.application.sandbox_agent_runner")

_CODE_FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def _build_prompt() -> str:
    """Build the generation prompt from the cache benchmark spec."""
    fields_list = ", ".join(REQUIRED_FIELDS)
    return textwrap.dedent(f"""\
        Generate a complete, self-contained Python module that defines a cache
        metrics domain type. The module MUST contain exactly:

        1. A `CacheNodeKind` StrEnum (from `enum import StrEnum`) with at least
           three values (e.g. ENTRY, EVICTION, POLICY). Include a docstring.

        2. A `CacheMetrics` frozen dataclass (`@dataclass(frozen=True)`) with
           exactly these fields in order: {fields_list}
           All fields are non-negative ints. Include a docstring explaining that
           hit_count is the primary axis (higher = better, inverse).

        3. A `better_than(self, other: CacheMetrics) -> bool` method on
           CacheMetrics: returns True if self.hit_count > other.hit_count, or
           if equal hit_count and self.miss_count < other.miss_count.

        Return ONLY the Python code in a single ```python fenced block. No
        explanation, no imports beyond stdlib (dataclasses, enum).
        """)


def _extract_code(raw_text: str) -> str:
    """Extract Python source from a model response (strip markdown fences)."""
    match = _CODE_FENCE_RE.search(raw_text)
    if match:
        return match.group(1).strip()
    # No fence — assume the whole response is code (best effort).
    return raw_text.strip()


@dataclass(frozen=True)
class SandboxRunResult:
    """Outcome of a single sandbox agent run.

    Carries the Loop (with lifecycle events), the verifier fitness, the model
    used, the path to the generated candidate, and any error.
    """

    loop: Loop
    fitness: SandboxFitness
    model: str
    generated_path: str | None = None
    error: str | None = None


class SandboxAgentRunner:
    """Run the cache benchmark with ONE model: prompt → generate → verify → Loop.

    Usage::

        runner = SandboxAgentRunner(provider=my_provider, sandbox_dir=tmp)
        result = runner.run(model="minimax/MiniMax-M3")
    """

    def __init__(self, *, provider: LLMProviderPort, sandbox_dir: str | Path = "runs/sandbox") -> None:
        if provider is None:
            raise TypeError("provider must be a non-None LLMProviderPort")
        if not hasattr(provider, "complete") or not hasattr(provider, "default_model"):
            raise TypeError("provider must satisfy LLMProviderPort (complete + default_model)")
        self._provider = provider
        self._sandbox_dir = Path(sandbox_dir)
        self._counter = 0

    def run(
        self,
        *,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        timeout_seconds: float = 60.0,
    ) -> SandboxRunResult:
        """Generate + verify a cache_types candidate. Returns a SandboxRunResult."""
        resolved_model = model or self._provider.default_model
        self._counter += 1
        run_id = f"sandbox-run-{self._counter}"

        loop = Loop.start(
            id=run_id,
            intent=f"Generate cache_types via {resolved_model}",
            budget=Budget(max_llm_calls=1, max_cost=0.05),
            skills=("sandbox-cache-task",),
        )

        # ── Generate ────────────────────────────────────────────────────
        prompt = _build_prompt()
        try:
            response = self._provider.complete(
                system="You are a Python code generator. Output only code.",
                messages=[LLMMessage(role="user", content=prompt)],
                model=resolved_model,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=1.0,
                output_schema=None,
                timeout_seconds=timeout_seconds,
            )
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"
            _log.warning("sandbox run %s LLM failed: %s", run_id, error)
            failed_loop = loop.advance(
                LoopEvent.now(LoopEventKind.FAILED, LoopState.FAILED, {"error": error})
            )
            return SandboxRunResult(
                loop=failed_loop,
                fitness=_zero_fitness(),
                model=resolved_model,
                error=error,
            )

        raw_text = getattr(response, "raw_text", "") or str(response)
        code = _extract_code(raw_text)

        # ── Write candidate ─────────────────────────────────────────────
        self._sandbox_dir.mkdir(parents=True, exist_ok=True)
        candidate_path = self._sandbox_dir / f"{run_id}_cache_types.py"
        candidate_path.write_text(code, encoding="utf-8")
        _autofix(candidate_path)

        # ── Verify ──────────────────────────────────────────────────────
        fitness = verify_candidate(candidate_path)

        # ── Record Loop outcome ─────────────────────────────────────────
        if fitness.score == 1.0:
            final_loop = loop.advance(
                LoopEvent.now(LoopEventKind.VERIFIED, LoopState.VERIFYING, {"verifier": "sandbox-verifier"})
            )
            final_loop = final_loop.advance(
                LoopEvent.now(LoopEventKind.FINISHED, LoopState.DONE, {"score": fitness.score})
            )
        else:
            final_loop = loop.advance(
                LoopEvent.now(
                    LoopEventKind.FAILED, LoopState.FAILED,
                    {"score": fitness.score, "axes": fitness.axes()},
                )
            )

        _log.info("sandbox run %s model=%s score=%.2f", run_id, resolved_model, fitness.score)
        return SandboxRunResult(
            loop=final_loop,
            fitness=fitness,
            model=resolved_model,
            generated_path=str(candidate_path),
        )


def _zero_fitness() -> SandboxFitness:
    """Fitness for a failed run (all axes False)."""
    f = SandboxFitness(
        structure_ok=False, invariants_ok=False, ranking_ok=False, ruff_clean=False,
    )
    f.loc_ok = False
    f.score = 0.0
    return f


def _autofix(path: Path) -> None:
    """Run ruff format + check --fix on the generated candidate.

    Models frequently emit unsorted imports or trivial style issues; this
    normalises them before verification so the fitness measures the semantic
    quality of the candidate, not its formatting. Best-effort: failures are
    ignored (the verifier will still score ruff_clean=False).
    """
    import subprocess

    try:
        subprocess.run(
            ["uv", "run", "ruff", "format", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        subprocess.run(
            ["uv", "run", "ruff", "check", "--fix", str(path)],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.SubprocessError, OSError):
        pass  # best-effort; verifier will report ruff_clean=False
