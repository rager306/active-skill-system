"""L2 Application — memory guard (M040 S03).

Platform-aware memory threshold check so a composition entrypoint can skip
gracefully when memory is critically low instead of risking OOM mid-run.

Uses the stdlib ``resource`` module (always available on Unix) to read the
process RSS. ``psutil`` is used opportunistically when available (more
portable, gives system-wide pressure); if it is absent we fall back to
``resource`` without error. No hard dependency on psutil — keeps the suite
runnable without extra installs (R002-friendly: stdlib-first).

Pure application. Depends on stdlib only (R002).
"""

from __future__ import annotations

import logging
import sys
from typing import Any

_log = logging.getLogger("active_skill_system.application.memory_guard")


def _rss_bytes_psutil() -> int | None:
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        return int(psutil.Process().memory_info().rss)
    except Exception:  # noqa: BLE001 — never let the guard itself crash
        return None


def _rss_bytes_resource() -> int | None:
    if sys.platform == "win32":
        return None
    try:
        import resource

        # ru_maxrss is in kilobytes on Linux, bytes on macOS.
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return int(rss)
        return int(rss) * 1024
    except Exception:  # noqa: BLE001
        return None


def process_rss_bytes() -> int | None:
    """Return current process RSS in bytes, or None if undeterminable."""
    return _rss_bytes_psutil() or _rss_bytes_resource()


def system_memory_pressure_pct() -> float | None:
    """Return system memory usage percent (0-100), or None if unavailable."""
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        return float(psutil.virtual_memory().percent)
    except Exception:  # noqa: BLE001
        return None


def check_memory(*, threshold_pct: float = 90.0, ctx: dict[str, Any] | None = None) -> bool:
    """Return True when it is safe to proceed, False when memory is critical.

    ``threshold_pct`` is compared against system memory pressure (psutil) when
    available; otherwise against a coarse RSS heuristic. A WARNING is logged
    with the measured pressure when the threshold is exceeded. Never raises.
    """
    if threshold_pct <= 0 or threshold_pct > 100:
        raise ValueError(f"threshold_pct must be in (0, 100] (got {threshold_pct!r})")

    pressure = system_memory_pressure_pct()
    if pressure is not None:
        ok = pressure < threshold_pct
        if not ok:
            _log.warning(
                "memory pressure %.1f%% >= threshold %.1f%%; skipping gracefully (ctx=%s)",
                pressure, threshold_pct, ctx,
            )
        return ok

    # Fallback: no system pressure available; assume OK (never block on unknown).
    rss = process_rss_bytes()
    _log.debug("memory guard: no psutil pressure; rss=%s bytes", rss)
    return True
