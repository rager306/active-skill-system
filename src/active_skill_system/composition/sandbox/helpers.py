"""L4 Composition — sandbox helpers (M052 S00).

Shared utilities used across sandbox CLI modules.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

_sandbox_logger: logging.Logger | None = None


def get_sandbox_logger() -> logging.Logger:
    """Lazy module-level sandbox session logger (M049)."""
    global _sandbox_logger
    if _sandbox_logger is not None:
        return _sandbox_logger
    log_dir = Path(os.environ.get("SANDBOX_LOG_DIR", "logs/sandbox"))
    log_dir.mkdir(parents=True, exist_ok=True)
    session_ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    sandbox_log_path = log_dir / f"sandbox-{session_ts}.log"
    logger = logging.getLogger("sandbox.session")
    if not any(
        isinstance(h, logging.FileHandler)
        and getattr(h, "baseFilename", "") == str(sandbox_log_path)
        for h in logger.handlers
    ):
        fh = logging.FileHandler(sandbox_log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)sZ %(levelname)s %(message)s"))
        logger.addHandler(fh)
        logger.setLevel(logging.INFO)
    print(f"sandbox log: {sandbox_log_path}", flush=True)
    _sandbox_logger = logger
    return logger
