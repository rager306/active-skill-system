"""L2 Application use-case — CompilerGapDetector (M016 S03 T01).

Classifies the current state of a compiler optimization loop into a
:class:`CompilerGapClass` (or a "no improvement yet" / "improved" sentinel).

Pure function. NO I/O, NO infrastructure imports (R002).

Classification rules (applied in order):

  1. ``previous is None`` (first iteration, no candidate tried yet)
     → :attr:`CompilerGapClass.MISSING_TRANSFORM`
  2. ``current.is_valid is False`` (transform produced an unschedulable schedule)
     → :attr:`CompilerGapClass.REGISTER_SPILL`
  3. :meth:`CompilerMetrics.better_than` says current improved over previous
     → a sentinel :data:`NO_GAP` (callers should treat this as "stop, success")
  4. Both cycles and spills regressed vs previous
     → :attr:`CompilerGapClass.PERF_REGRESSION`
  5. Cycles improved but spills got strictly worse (> 2× increase)
     → :attr:`CompilerGapClass.REGISTER_SPILL`
  6. Cycles regressed while spills improved
     → :attr:`CompilerGapClass.TRANSFORM_REGRESSION`
  7. Otherwise (no meaningful movement, or partial trade-off)
     → :attr:`CompilerGapClass.MISSING_TRANSFORM`

The sentinel is exported as :data:`NO_GAP` — a string constant, NOT a new
:class:`CompilerGapClass` value. Extending the enum would muddy the
"taxonomy of failure modes" semantics of ``CompilerGapClass``; a clean
sentinel keeps the domain small and the loop driver explicit.
"""

from __future__ import annotations

from typing import Final

from active_skill_system.domain.compiler_types import (
    CompilerGapClass,
    CompilerMetrics,
)

# Sentinel meaning "current beats previous — no gap to repair".
# Callers (loop driver) compare to this value rather than treating
# any CompilerGapClass value as a success signal.
NO_GAP: Final[str] = "__no_gap__"

# Spills-regression threshold for REGISTER_SPILL rule (cycles improved but
# spills more than doubled). Exposed as a module constant so tests can
# reference the exact value.
SPILLS_REGRESSION_RATIO: Final[float] = 2.0


def is_improved(previous: CompilerMetrics, current: CompilerMetrics) -> bool:
    """True if ``current`` is strictly better than ``previous`` per ``better_than``."""
    return current.better_than(previous)


def classify_gap(
    previous: CompilerMetrics | None,
    current: CompilerMetrics,
) -> CompilerGapClass | str:
    """Classify the current state of the optimization loop.

    Args:
      previous: metrics from the prior iteration; ``None`` if this is the
        first iteration (no candidate has been tried yet).
      current: metrics just produced by applying the latest candidate.

    Returns:
      Either :data:`NO_GAP` (current strictly improved on BOTH axes vs
      previous — the loop driver should accept and stop), or a
      :class:`CompilerGapClass` value describing what is wrong.

    Pure function. NO I/O.

    Note: this classifier does NOT delegate to
    :meth:`CompilerMetrics.better_than` because that method ranks by
    cycles-first and treats spills as a tie-breaker — which would hide
    spill regressions that are worth flagging as their own gap class.
    """
    # Rule 2: invalid schedule is always a spill-style failure first.
    if not current.is_valid:
        return CompilerGapClass.REGISTER_SPILL

    # Rule 1: first iteration, no candidate tried yet.
    if previous is None:
        return CompilerGapClass.MISSING_TRANSFORM

    cycles_improved = current.cycles < previous.cycles
    cycles_regressed = current.cycles > previous.cycles
    spills_improved = current.spills < previous.spills
    spills_regressed = current.spills > previous.spills

    # Rule 3a: cycles improved AND spills did not regress → true win.
    if cycles_improved and not spills_regressed:
        return NO_GAP

    # Rule 4: both axes regressed.
    if cycles_regressed and spills_regressed:
        return CompilerGapClass.PERF_REGRESSION

    # Rule 5: cycles improved but spills got strictly worse (> 2× increase).
    if cycles_improved and spills_regressed:
        if previous.spills > 0 and current.spills > previous.spills * SPILLS_REGRESSION_RATIO:
            return CompilerGapClass.REGISTER_SPILL
        if previous.spills == 0 and current.spills > 0:
            # Spills went from 0 to anything non-zero — also a regression.
            return CompilerGapClass.REGISTER_SPILL
        # Tolerable trade-off: cycles improved a lot, spills bumped slightly.
        return CompilerGapClass.MISSING_TRANSFORM

    # Rule 6: cycles regressed while spills improved — wrong direction.
    if cycles_regressed and spills_improved:
        return CompilerGapClass.TRANSFORM_REGRESSION

    # Rule 7: cycles regressed but spills unchanged → overall perf regression.
    if cycles_regressed:
        return CompilerGapClass.PERF_REGRESSION

    # Rule 7b: no meaningful movement (or a tolerable trade-off).
    return CompilerGapClass.MISSING_TRANSFORM
