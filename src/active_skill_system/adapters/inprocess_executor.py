"""L3 Adapter — InProcessExecutor (M044 S01 T02, D018).

The backward-compatible code executor: loads a candidate module via importlib
in the current process. Acceptable ONLY for deterministic offline tests where
the candidate source is known (fixtures, FakeReasoningEngine). For real-LLM
generated code, use BwrapExecutor (isolated).

This adapter encapsulates the importlib + sys.modules-registration logic
previously inlined in sandbox_verifier.
"""

from __future__ import annotations

import importlib.util
import sys

from active_skill_system.application.ports.code_executor import (
    ExecutionResult,
)


class InProcessExecutor:
    """Importlib-backed code executor (no isolation — for offline tests only).

    Implements CodeExecutorPort. Loads the candidate module via importlib,
    registering it in sys.modules during exec so @dataclass decorators do not
    crash (the importlib + dataclasses.fields() edge case, M042 S01).
    """

    def execute(self, code_path: str, *, timeout: float = 30.0) -> ExecutionResult:
        """Load a candidate module in-process. Returns ExecutionResult."""
        spec = importlib.util.spec_from_file_location("_sandbox_candidate", code_path)
        if spec is None or spec.loader is None:
            return ExecutionResult(error=f"cannot load module from {code_path}", exit_code=1)
        module = importlib.util.module_from_spec(spec)
        sys.modules["_sandbox_candidate"] = module
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(error=f"{type(exc).__name__}: {exc}", exit_code=1)
        finally:
            sys.modules.pop("_sandbox_candidate", None)
        return ExecutionResult(stdout="OK")


# InProcessExecutor structurally satisfies CodeExecutorPort.
# (Runtime check omitted — no constructor side effects.)
