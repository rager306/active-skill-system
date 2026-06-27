"""L4 Composition — mini sandbox entrypoint (M042 S01 T03, D013 mini-loop).

Currently exposes ``--check``: score a candidate cache_types module against the
deterministic verifier (no LLM). S02/S03 extend this with ``--model`` /
``--models`` for real-LLM multi-model runs.

R008/R009: stdlib-only module-level imports; the verifier is imported lazily
inside ``main``. Importing this module is side-effect free.

Usage::

    uv run python -m active_skill_system.composition.mini_sandbox --check \\
        tests/fixtures/sandbox/cache_full.py
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="active-skill-mini-sandbox",
        description=(
            "D013 mini-loop sandbox. --check scores a candidate module "
            "deterministically (ruff+ty+pyrefly+riskratchet+structure). "
            "Multi-model --models arrives in S03."
        ),
    )
    parser.add_argument(
        "--check",
        type=str,
        default=None,
        help="Path to a candidate cache_types module to score.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    from active_skill_system.composition.logging_config import configure_logging
    from active_skill_system.application.use_cases.sandbox_verifier import verify_candidate

    configure_logging()

    if args.check is None:
        print("nothing to do: pass --check <path> (or --model/--models in S02/S03)", flush=True)
        return 0

    fitness = verify_candidate(args.check)
    axes = fitness.axes()
    print(f"candidate: {args.check}", flush=True)
    print(f"score: {axes['score']:.2f}", flush=True)
    for name, val in axes.items():
        if name != "score":
            print(f"  {name}: {val}", flush=True)
    return 0 if axes["score"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
