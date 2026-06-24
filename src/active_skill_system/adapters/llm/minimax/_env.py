"""Environment loading for the MiniMax adapter.

Extracted from the former monolithic ``minimax.py`` so the env-loading
concern stays small, testable, and side-effect-free at import time.
Loads the project ``.env`` (chmod 600, gitignored) that carries the
MiniMax gateway credentials:

  - ``ANTHROPIC_BASE_URL`` (https://api.minimax.io/anthropic)
  - ``ANTHROPIC_AUTH_TOKEN`` (Bearer; the Anthropic SDK reads it)
  - ``ANTHROPIC_MODEL`` (MiniMax-M3-512k / MiniMax-M3)

Depends only on stdlib + python-dotenv.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def _project_root() -> Path:
    """Walk up from this file to the directory containing ``pyproject.toml``."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return here.parents[3]


PROJECT_ROOT = _project_root()
ENV_PATH = PROJECT_ROOT / ".env"


def load_env(env_path: Path | str = ENV_PATH) -> os._Environ:
    """Load the project ``.env`` into ``os.environ`` (override=True).

    Returns the environment so callers can read the resolved keys.
    """
    load_dotenv(str(env_path), override=True)
    return os.environ
