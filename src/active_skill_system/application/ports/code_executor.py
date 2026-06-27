"""L2 Application — CodeExecutorPort (M044, D018).

Generic code-execution isolation seam. All execution backends (InProcess,
BwrapExecutor, future NsJail/Pyodide) implement this Protocol. The application
depends on this port, never on a concrete executor or subprocess (R002).

D018 security context: the sandbox generates LLM code and must execute it
isolated. InProcessExecutor (importlib) is acceptable ONLY for deterministic
offline tests; BwrapExecutor (bubblewrap namespaces) is the production floor.

Pure application. Depends on stdlib only (R002).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of executing a candidate code module.

    Carries:
      - stdout: captured standard output from the execution.
      - exit_code: process exit code (0 = success).
      - error: None on success; an error message on failure.
    """

    stdout: str = ""
    exit_code: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        """True when execution succeeded (exit 0, no error)."""
        return self.error is None and self.exit_code == 0


@runtime_checkable
class CodeExecutorPort(Protocol):
    """Generic code-execution isolation contract (D018).

    Implementations (InProcessExecutor, BwrapExecutor, future NsJail/Pyodide)
    live in L3 adapters and are wired at composition time. The application
    depends on this Protocol, never on a concrete executor.
    """

    def execute(self, code_path: str, *, timeout: float = 30.0) -> ExecutionResult:
        """Execute a candidate code module and return the result.

        Implementations MUST catch internal errors and return an
        ExecutionResult with ``error`` set — never raise to the caller.
        """
        ...
