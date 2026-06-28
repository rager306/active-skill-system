#!/usr/bin/env bash
# PreVerify hook: run self-governance check on our own codebase.
#
# The project validates ITSELF using its own verification tools:
#   - lint-imports (layering contracts R001/R002/R007)
#   - ruff (lint clean)
#   - ty + pyrefly (type-check clean)
#   - riskratchet (risk baseline not regressed R010/R011)
#   - GitNexus convention check (new code matches existing patterns)
#   - pytest (test suite green)
#   - AST docstring check (public symbols documented)
#
# This is recursive dogfooding: the system that builds verification
# tools uses those same tools on itself during development.
#
# Exit code mapping (composition/cli_exit.py):
#   EX_OK (0)        → allow (all 8 governance axes passed)
#   EX_PARTIAL (1)   → block (one or more axes failed — code not ready)
#
# Event payload arrives on stdin as JSON. GSD_HOOK_EVENT/SCOPE set by GSD.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

# Load .env for paths.
if [ -f .env ]; then
  set -a; source .env 2>/dev/null || true; set +a
fi

# Drain stdin (event payload).
cat >/dev/null 2>&1 || true

# ── Self-governance check ───────────────────────────────────────────
set +e
output="$(uv run python -m active_skill_system.composition.mini_sandbox \
  --governance-check 2>&1)"
exit_code=$?
set -e

case $exit_code in
  0)
    echo "PreVerify: governance check PASSED (all axes OK)" >&2
    exit 0
    ;;
  1)
    echo '{"block": true, "reason": "governance check EX_PARTIAL: one or more verification axes failed — see hook stderr"}'
    echo "--- governance check output ---" >&2
    echo "$output" | grep -E 'governance|OK|FAIL|score' >&2
    exit 1
    ;;
  *)
    echo "{\"block\": true, \"reason\": \"governance check unexpected exit $exit_code\"}"
    echo "$output" | tail -10 >&2
    exit 1
    ;;
esac
