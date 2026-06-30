"""L4 Composition — sandbox CLI dispatch (M052 S00).

Argument parsing + dispatch routing. Thin layer over sandbox/ sub-modules.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from active_skill_system.composition.cli_exit import EX_USAGE
from active_skill_system.composition.sandbox.governance import (
    build_event_store,
    run_event_stats,
    run_governance_check,
)
from active_skill_system.composition.sandbox.graphs import (
    run_graph_query,
    run_graph_stats,
    run_graph_trajectory,
    run_ratchet_stats,
)
from active_skill_system.composition.sandbox.helpers import get_sandbox_logger
from active_skill_system.composition.sandbox.queries import (
    run_compare_runs,
    run_recommend,
    run_report,
)
from active_skill_system.composition.sandbox.runs import (
    run_check,
    run_multi_model,
    run_program_bench,
    run_single_model,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the sandbox entrypoint."""
    parser = argparse.ArgumentParser(
        prog="active-skill-mini-sandbox",
        description="D013 mini-loop sandbox with governance, provenance, and fork-diff.",
    )
    parser.add_argument("--check", type=str, default=None, help="Score a candidate module (no LLM).")
    parser.add_argument("--model", type=str, default=None, help="Run ONE model on the benchmark.")
    parser.add_argument("--models", type=str, default=None, help="Comma-separated model list.")
    parser.add_argument("--executor", type=str, default="inprocess", choices=("inprocess", "bwrap"))
    _default_graph = os.environ.get("SANDBOX_GRAPH_PATH", "runs/sandbox_graph.lbdb")
    parser.add_argument("--graph", type=str, default=_default_graph)
    _default_ratchet = os.environ.get("SANDBOX_RATCHET_PATH", "runs/ratchet.jsonl")
    parser.add_argument("--ratchet", type=str, default=_default_ratchet)
    parser.add_argument("--graph-query", type=str, default=None)
    parser.add_argument("--graph-stats", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--compare-runs", nargs=2, metavar=("ID_A", "ID_B"), default=None)
    parser.add_argument("--recommend", action="store_true")
    parser.add_argument("--graph-trajectory", action="store_true")
    parser.add_argument("--ratchet-stats", action="store_true")
    parser.add_argument("--strategy", type=str, default="plain", choices=("plain", "dspy", "fast-rlm"))
    parser.add_argument("--bench", type=str, default=None, choices=("cache-types", "program-bench"))
    parser.add_argument("--event-log", type=str, default=None)
    parser.add_argument("--event-stats", action="store_true")
    parser.add_argument("--governance-check", action="store_true")
    parser.add_argument("--fork", nargs=2, metavar=("RUN_ID", "AT_EVENT"), default=None,
                        help="Fork a run at a specific event.")
    parser.add_argument("--fork-model", type=str, default=None,
                        help="Model override for forked run (use with --fork).")
    parser.add_argument("--diff", nargs=2, metavar=("RUN_A", "RUN_B"), default=None,
                        help="Structural diff of two runs.")
    parser.add_argument("--behaviors", action="store_true",
                        help="Enable reactive behavior mode (events trigger behaviors).")
    parser.add_argument("--behavior-demo", action="store_true",
                        help="Run reactive behavior demo (creates claim, fires behaviors).")
    return parser.parse_args(argv)


def load_env() -> None:
    """Load .env so SANDBOX_* paths are available."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def dispatch(args: argparse.Namespace) -> int:
    """Route parsed args to the correct handler."""
    if args.ratchet_stats:
        return run_ratchet_stats(args.ratchet or "runs/ratchet.jsonl")
    if args.graph_trajectory:
        return run_graph_trajectory(args.graph)
    if args.graph_query is not None:
        return run_graph_query(args.graph, args.graph_query)
    if args.graph_stats:
        return run_graph_stats(args.graph)
    if args.report:
        return run_report(args.graph, args.ratchet, args.json, os.environ.get("SANDBOX_LOG_DIR"))
    if args.compare_runs is not None:
        return run_compare_runs(args.graph, args.compare_runs[0], args.compare_runs[1], args.json, os.environ.get("SANDBOX_LOG_DIR"))
    if args.recommend:
        return run_recommend(args.graph, args.ratchet, args.json, os.environ.get("SANDBOX_LOG_DIR"))
    if args.event_stats:
        return run_event_stats(args.event_log or os.environ.get("SANDBOX_EVENT_LOG", ""))
    if args.governance_check:
        return run_governance_check()
    if args.fork is not None:
        from active_skill_system.composition.sandbox.fork_ops import run_fork

        return run_fork(args.fork[0], args.fork[1], args.fork_model, args.event_log)
    if args.diff is not None:
        from active_skill_system.composition.sandbox.fork_ops import run_diff

        return run_diff(args.diff[0], args.diff[1], args.event_log)
    if args.behavior_demo:
        from active_skill_system.composition.sandbox.reactive_ops import run_behavior_demo

        return run_behavior_demo(args.event_log)
    if args.check is not None:
        return run_check(args.check)
    if args.model is not None:
        if args.bench == "program-bench":
            return run_program_bench(args.model, args.executor, args.graph, args.ratchet, args.strategy)
        event_store = build_event_store(args.event_log or os.environ.get("SANDBOX_EVENT_LOG"))
        return run_single_model(args.model, args.executor, args.graph, args.ratchet, args.strategy, event_store)
    if args.models is not None:
        return run_multi_model(args.models, args.graph)
    print("nothing to do: pass --check / --model / --models", flush=True)
    return EX_USAGE


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: parse args, dispatch to the appropriate handler."""
    args = parse_args(argv)
    load_env()
    from active_skill_system.composition.logging_config import configure_logging

    configure_logging()
    get_sandbox_logger().info(
        "session_start model=%s executor=%s graph=%s", args.model, args.executor, args.graph,
    )
    return dispatch(args)
