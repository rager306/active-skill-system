"""L4 Composition — logging configuration (M040 S01).

Unified logging backbone. Library code (domain + application) uses stdlib
``logging.getLogger(__name__)`` so it stays R002-clean (no third-party dep in
those layers). This module — composition only — installs a loguru
``InterceptHandler`` so every stdlib logger routes through loguru, then adds a
rotating file sink (driven by ``LOG_DIR`` from the environment) plus a stderr
sink for development.

Discipline:
  - ``loguru`` is imported ONLY here (composition). An AST guard in the test
    suite asserts no domain/application module imports it.
  - ``configure_logging`` is called inside ``main()`` of composition
    entrypoints (R008: importing a composition module has no side effects).
  - Secrets are never logged: only ``LOG_DIR`` and non-secret config are read.

LOG_DIR resolution: ``LOG_DIR`` env var (default ``logs``). python-dotenv loads
``.env`` at composition time; here we read the already-populated environment.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_MAX_BYTES = 10 * 1024 * 1024  # 10 MB rotation threshold
_RETENTION = 5  # keep 5 rotated files
_DEFAULT_LOG_DIR = "logs"


def get_log_dir() -> str:
    """Return the configured log directory (LOG_DIR env var, default 'logs')."""
    return os.environ.get("LOG_DIR", _DEFAULT_LOG_DIR)


class InterceptHandler(logging.Handler):
    """Route stdlib ``logging`` records into loguru.

    Installed as a handler on the stdlib root logger so every
    ``logging.getLogger(__name__)`` call in domain/application is captured by
    the loguru sink chain (file + stderr).
    """

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        # Local import keeps loguru out of module top-level side effects.
        from loguru import logger

        # Map stdlib level to loguru level (loguru accepts names + numbers).
        try:
            level: str | int = logger.level(record.levelname).name
        except (ValueError, TypeError):
            level = record.levelno

        # Find the originating frame for correct depth/caller info.
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging(
    *,
    level: str = "INFO",
    log_dir: str | None = None,
    dev_stderr: bool = True,
) -> Path:
    """Install loguru intercept of stdlib logging + rotating file sink.

    Args:
        level: minimum log level (default INFO).
        log_dir: directory for the rotating file sink; defaults to LOG_DIR env.
        dev_stderr: also emit to stderr (handy for CLI/dev).

    Returns:
        The path of the configured file sink.

    Idempotent: re-installing replaces handlers rather than duplicating them.
    """
    from loguru import logger

    directory = Path(log_dir if log_dir is not None else get_log_dir())
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / "app.log"

    logger.remove()
    logger.add(
        str(log_path),
        level=level,
        rotation=_MAX_BYTES,
        retention=_RETENTION,
        enqueue=True,  # thread-safe writes; never blocks the caller
        backtrace=True,
        diagnose=False,  # avoid leaking local vars (secrets) in tracebacks
    )
    if dev_stderr:
        logger.add(sys.stderr, level=level, backtrace=True, diagnose=False)

    # Route stdlib logging → loguru.
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    return log_path
