"""L4 Composition — CLI exit code constants (M049 S04).

Single source of truth for mini_sandbox exit codes. Every CLI mode returns
one of these. Tests assert on them so callers can rely on the contract.

Convention follows BSD sysexits.h loosely:
  EX_OK        (0) — success
  EX_PARTIAL   (1) — partially succeeded (some data, some warnings)
  EX_NOT_FOUND (2) — required resource missing (graph, ratchet, run id)
  EX_USAGE     (3) — user-supplied args invalid (future)
"""

from __future__ import annotations

EX_OK: int = 0
EX_PARTIAL: int = 1
EX_NOT_FOUND: int = 2
EX_USAGE: int = 3

ALL_EXIT_CODES: tuple[int, ...] = (EX_OK, EX_PARTIAL, EX_NOT_FOUND, EX_USAGE)


def name_for(code: int) -> str:
    """Return the constant name for a given exit code, or 'EX_UNKNOWN'."""
    for name, value in (
        ("EX_OK", EX_OK),
        ("EX_PARTIAL", EX_PARTIAL),
        ("EX_NOT_FOUND", EX_NOT_FOUND),
        ("EX_USAGE", EX_USAGE),
    ):
        if value == code:
            return name
    return "EX_UNKNOWN"
