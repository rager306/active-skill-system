"""Layering contract: import-linter enforces the onion/hexagonal architecture.

Run as part of the default suite so a forbidden dependency (e.g. domain
importing activegraph) fails the build. See pyproject.toml [tool.importlinter].
"""

from __future__ import annotations

import shutil
import subprocess


def _lint_imports_bin() -> str:
    # prefer the venv console script; fall back to uv run
    venv_bin = shutil.which("lint-imports")
    return venv_bin or "lint-imports"


def test_layering_contracts_kept() -> None:
    cmd = [_lint_imports_bin()]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        "import-linter contracts broken:\n"
        + combined
        + "\nRun `uv run lint-imports` for the graph."
    )
    assert "Contracts:" in combined and "0 broken" in combined, combined
