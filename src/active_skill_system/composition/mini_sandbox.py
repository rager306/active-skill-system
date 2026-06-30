"""L4 Composition — mini sandbox entrypoint (M042, D013 mini-loop).

Thin entrypoint that delegates to the composition.sandbox package (M052 S00).
Split from the original 807 LOC monolith into:
  sandbox/cli.py       — parse_args, dispatch, main
  sandbox/runs.py      — run_single_model, run_multi_model, run_program_bench
  sandbox/queries.py   — run_report, run_compare_runs, run_recommend
  sandbox/governance.py — run_governance_check, run_event_stats, build_event_store
  sandbox/graphs.py    — run_graph_stats, run_graph_query, run_graph_trajectory, run_ratchet_stats
  sandbox/helpers.py   — get_sandbox_logger

Usage::

    uv run python -m active_skill_system.composition.mini_sandbox --model minimax/MiniMax-M3
"""

from __future__ import annotations

from active_skill_system.composition.sandbox.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
