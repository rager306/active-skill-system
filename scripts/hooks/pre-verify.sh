#!/usr/bin/env bash
# PreVerify hook: run OUR composition CLI as the verification signal.
# The exit code from mini_sandbox IS the gate verdict — no manual interpretation.
#
# Exit code mapping (composition/cli_exit.py):
#   EX_OK (0)        → allow (all good)
#   EX_PARTIAL (1)   → block (candidate failed / partial)
#   EX_NOT_FOUND (2) → block (graph/ratchet/run missing)
#   EX_USAGE (3)     → block (bad invocation)
#
# Event payload arrives on stdin as JSON. GSD_HOOK_EVENT/SCOPE set by GSD.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

# Load .env for SANDBOX_* paths.
if [ -f .env ]; then
  set -a; source .env 2>/dev/null || true; set +a
fi

# Drain stdin (event payload) — we don't parse it yet.
cat >/dev/null 2>&1 || true

# ── Run our composition CLI as the domain-specific gate ─────────────
# --check scores the reference fixture deterministically (no LLM, ~1s).
# This proves the verifier pipeline + graph + ports are all wired correctly.
# If this fails, the whole sandbox foundation is broken — block verification.
output="$(uv run python -m active_skill_system.composition.mini_sandbox \
  --check tests/fixtures/sandbox/cache_full.py 2>&1 || true)"
exit_code=$?

case $exit_code in
  0)
    echo "PreVerify: mini_sandbox --check OK (score 1.00)" >&2
    exit 0
    ;;
  1)
    echo '{"block": true, "reason": "mini_sandbox --check EX_PARTIAL: candidate scored below 1.0 — sandbox verifier pipeline degraded"}'
    echo "--- mini_sandbox output ---" >&2
    echo "$output" >&2
    exit 1
    ;;
  2)
    echo '{"block": true, "reason": "mini_sandbox --check EX_NOT_FOUND: fixture or graph resource missing"}'
    echo "--- mini_sandbox output ---" >&2
    echo "$output" >&2
    exit 1
    ;;
  3)
    echo '{"block": true, "reason": "mini_sandbox --check EX_USAGE: invalid CLI invocation"}'
    exit 1
    ;;
  *)
    echo "{\"block\": true, \"reason\": \"mini_sandbox --check unexpected exit code $exit_code\"}"
    echo "$output" >&2
    exit 1
    ;;
esac
