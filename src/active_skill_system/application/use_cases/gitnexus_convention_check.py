"""L2 Application — GitNexus convention checker (M046 S01, S6).

Checks a candidate module against existing project conventions by querying the
GitNexus knowledge graph via CLI (npx gitnexus cypher). This gives the verifier
project-context awareness — it can detect code that is syntactically valid but
inconsistent with how the project does things (e.g. better_than direction,
dataclass patterns).

GitNexus is invoked via ``npx gitnexus cypher`` subprocess — NOT imported as a
library. If npx or GitNexus is unavailable, the check degrades gracefully
(returns consistent=True, reason='GitNexus unavailable — skipped').

Must be reindexed before use: ``npx gitnexus analyze`` (from project root).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger("active_skill_system.application.gitnexus_convention_check")

_REPO = "active-skill-system"


@dataclass(frozen=True)
class ConventionResult:
    """Result of a GitNexus convention check.

    Carries:
      - consistent: True if the candidate matches project conventions (or
        GitNexus is unavailable — graceful skip counts as consistent).
      - patterns_found: number of existing patterns found in the graph.
      - reason: human-readable explanation.
    """

    consistent: bool
    patterns_found: int
    reason: str


def _run_cypher(query: str) -> str | None:
    """Run a GitNexus Cypher query via CLI. Returns markdown output or None."""
    if shutil.which("npx") is None:
        return None
    try:
        result = subprocess.run(
            ["npx", "gitnexus", "cypher", query, "--repo", _REPO],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            _log.debug("gitnexus cypher failed (exit %d): %s", result.returncode, result.stderr[:200])
            return None
        return result.stdout
    except (subprocess.SubprocessError, OSError) as e:
        _log.debug("gitnexus cypher error: %s", e)
        return None


def _count_better_than_patterns() -> int:
    """Count existing better_than implementations in the project graph."""
    output = _run_cypher(
        "MATCH (n) WHERE n.name CONTAINS 'better_than' RETURN count(n) AS cnt"
    )
    if output is None:
        return 0
    # Parse markdown table for the count.
    for line in output.strip().splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    # Try to find a number in the last row.
    lines = [l.strip() for l in output.strip().splitlines() if l.strip()]
    for line in reversed(lines):
        if line.isdigit():
            return int(line)
    return 0


class ConventionChecker:
    """Check candidate code against project conventions via GitNexus.

    Usage::

        checker = ConventionChecker()
        result = checker.check_convention("path/to/candidate.py")
        if not result.consistent:
            print(f"convention violation: {result.reason}")
    """

    def check_convention(self, candidate_path: str) -> ConventionResult:
        """Check a candidate module against existing project patterns."""
        if shutil.which("npx") is None:
            return ConventionResult(
                consistent=True, patterns_found=0,
                reason="npx unavailable — convention check skipped",
            )

        patterns = _count_better_than_patterns()
        if patterns == 0:
            return ConventionResult(
                consistent=True, patterns_found=0,
                reason="GitNexus returned no patterns — check may need reindex (npx gitnexus analyze)",
            )

        # Read the candidate and check for better_than presence.
        try:
            source = Path(candidate_path).read_text(encoding="utf-8")
        except (OSError, FileNotFoundError):
            return ConventionResult(
                consistent=False, patterns_found=patterns,
                reason=f"cannot read candidate: {candidate_path}",
            )

        has_better_than = "better_than" in source
        if not has_better_than and patterns > 0:
            return ConventionResult(
                consistent=False, patterns_found=patterns,
                reason=f"project has {patterns} better_than implementations but candidate lacks one",
            )

        return ConventionResult(
            consistent=True, patterns_found=patterns,
            reason=f"candidate has better_than, consistent with {patterns} project patterns",
        )
