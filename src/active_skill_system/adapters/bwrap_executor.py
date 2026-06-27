"""L3 Adapter — BwrapExecutor (M044 S01 T03, D018).

Bubblewrap-isolated code executor. Runs a candidate module in a bubblewrap
namespace (--unshare-all, read-only system mounts, ephemeral /tmp, no network).
This is the D018 security floor for real-LLM-generated code.

bubblewrap v0.9.0 is installed in the environment. The executor constructs a
bwrap command that:
  - Mounts /usr, /lib, /lib64 read-only (Python runtime).
  - Binds an ephemeral /tmp (candidate + output).
  - Unshares all namespaces (pid, net, mount, user, ipc, uts).
  - Runs python3 to import the candidate and print OK on success.

No network access (--unshare-all includes net namespace). No write access
outside /tmp. Process dies with parent (--die-with-parent).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from active_skill_system.application.ports.code_executor import (
    ExecutionResult,
)

# Inline Python loader: imports the candidate module, prints OK, catches errors.
_LOADER = (
    "import importlib.util, sys; "
    "p = sys.argv[1]; "
    "spec = importlib.util.spec_from_file_location('candidate', p); "
    "m = importlib.util.module_from_spec(spec); "
    "sys.modules['candidate'] = m; "
    "spec.loader.exec_module(m); "
    "print('OK')"
)


class BwrapExecutor:
    """Bubblewrap-isolated code executor (production security floor, D018).

    Implements CodeExecutorPort. Runs candidate code inside a bwrap namespace
    with --unshare-all (no network, isolated mounts, separate PID namespace).
    """

    def execute(self, code_path: str, *, timeout: float = 30.0) -> ExecutionResult:
        """Execute a candidate module in a bubblewrap sandbox."""
        if not os.path.isfile(code_path):
            return ExecutionResult(error=f"candidate not found: {code_path}", exit_code=1)
        if shutil.which("bwrap") is None:
            return ExecutionResult(error="bubblewrap (bwrap) not installed", exit_code=1)

        # Ephemeral /tmp for the sandbox; copy the candidate there so it is
        # visible inside the namespace (the sandbox has no access to the host
        # working directory).
        sandbox_tmp = tempfile.mkdtemp(prefix="bwrap_sandbox_")
        candidate_copy = os.path.join(sandbox_tmp, "candidate.py")
        shutil.copy2(code_path, candidate_copy)
        try:
            return self._run_bwrap(candidate_copy, sandbox_tmp, timeout)
        finally:
            shutil.rmtree(sandbox_tmp, ignore_errors=True)

    def _run_bwrap(self, candidate_in_tmp: str, sandbox_tmp: str, timeout: float) -> ExecutionResult:
        """Build and run the bwrap command. candidate_in_tmp is relative to sandbox_tmp."""
        candidate_name = os.path.basename(candidate_in_tmp)
        cmd = [
            "bwrap",
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/lib64", "/lib64",
            "--ro-bind", "/bin", "/bin",
            "--bind", sandbox_tmp, "/tmp",
            "--dev", "/dev",
            "--proc", "/proc",
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "python3", "-c", _LOADER, f"/tmp/{candidate_name}",
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(error=f"execution timed out after {timeout}s", exit_code=124)
        except (subprocess.SubprocessError, OSError) as exc:
            return ExecutionResult(error=f"bwrap failed: {exc}", exit_code=1)

        if result.returncode == 0:
            return ExecutionResult(stdout=result.stdout.strip(), exit_code=0)
        error_msg = result.stderr.strip()[:500] if result.stderr else "unknown bwrap error"
        return ExecutionResult(error=error_msg, exit_code=result.returncode)
