"""L4 composition root — run the Diligence pack against MiniMax.

Wires the MiniMax adapter (L3) into the ActiveGraph runtime THROUGH the
application layer: ``RunReasoningUseCase`` + ``ActiveGraphRuntimeAdapter``,
so the entry point exercises the built layers instead of calling
``activegraph.Runtime`` directly.

A ``runtime_factory`` (closure) builds a configured ``Runtime`` — fresh Graph,
budget, persist_to, and the ``diligence`` pack loaded with settings — and
remembers it in a holder. The adapter calls the factory inside ``run_goal``;
after the use-case returns, the composition root reads the holder back to
persist state and print the trace (observability is an adapter concern, not a
use-case concern).

The goal MUST start with "Diligence:" (the company_planner guard) or the
reasoning cascade never fires.

Usage:
    uv run active-skill-diligence [company]
    .venv/bin/python -m active_skill_system.composition.diligence [company]

All infrastructure imports + side-effects (logging, env, runtime construction)
are deferred into ``main()`` (R008/R009) — importing this module is cheap and
side-effect free.
"""

from __future__ import annotations

import sys

from active_skill_system.adapters.llm.minimax import MiniMaxProvider, load_env
from active_skill_system.application.ports.runtime import Budget, RunGoal
from active_skill_system.application.use_cases.run_reasoning import RunReasoningRequest


def _build_factory(model: str):
    """Return a (factory, holder) pair.

    The factory produces a configured ``Runtime`` for a ``RunGoal`` and stashes
    it in ``holder`` so the composition root can read it back after the run
    (for save_state + trace). The diligence pack + settings are wired here.
    """
    # Lazy infra imports — only reached when a run actually starts.
    from activegraph import Graph, Runtime
    from activegraph.packs.diligence import DiligenceSettings
    from activegraph.packs.diligence import pack as diligence_pack

    holder: dict[str, object] = {}

    def factory(goal: RunGoal):
        graph = Graph()
        rt = Runtime(
            graph,
            llm_provider=None,  # injected per-run by the adapter (MiniMaxProvider)
            persist_to=goal.persist_to,
            budget={
                "max_llm_calls": 40,
                "max_tool_calls": 60,
                "max_cost_usd": "2.00",
            },
            seed=goal.seed if goal.seed is not None else 0,
        )
        rt.load_pack(
            diligence_pack,
            settings=DiligenceSettings(
                llm_model=model,
                max_documents_per_company=3,
                max_claims_per_document=6,
                confidence_threshold_for_review=0.7,
                min_questions=4,
                max_questions=6,
            ),
        )
        holder["runtime"] = rt
        return rt

    return factory, holder


def _default_wiring(model: str):
    """Build the production wiring: (use_case, holder).

    Extracted so tests can substitute a fake wiring (no network).
    """
    from active_skill_system.adapters.runtime.activegraph import ActiveGraphRuntimeAdapter
    from active_skill_system.application.use_cases.run_reasoning import RunReasoningUseCase

    factory, holder = _build_factory(model)
    runtime = ActiveGraphRuntimeAdapter(runtime_factory=factory)
    use_case = RunReasoningUseCase(runtime, llm_provider=MiniMaxProvider())
    return use_case, holder


def main(argv: list[str] | None = None, *, _wiring=None) -> int:
    from activegraph import configure_logging

    configure_logging(level="ERROR", json_output=False)

    argv = list(sys.argv[1:] if argv is None else argv)
    company = argv[0] if argv else "OpenAI"

    env = load_env()
    model = env.get("ANTHROPIC_MODEL", "MiniMax-M3")
    print(
        f"env: base_url={env.get('ANTHROPIC_BASE_URL')} "
        f"auth={'SET' if env.get('ANTHROPIC_AUTH_TOKEN') else 'MISSING'} "
        f"model={model}",
        flush=True,
    )

    # Wire the built layers: use-case + adapter + factory, MiniMax provider.
    # _wiring is an injection seam for tests (default = production wiring).
    use_case, holder = _wiring(model) if _wiring is not None else _default_wiring(model)

    print(f"running Diligence on '{company}' with {model} ...", flush=True)
    result = use_case.run(
        RunReasoningRequest(
            goal=f"Diligence: {company}",
            persist_to="diligence_run.db",
            seed=0,
            budget=Budget(max_llm_calls=40, max_tool_calls=60, max_cost_usd="2.00"),
        )
    )

    # Observability via the holder (adapter concern, not use-case concern).
    rt = holder.get("runtime")
    if rt is not None:
        rt.save_state()
    print(f"RUN {result.status.upper()} (run_id={result.run_id}, events={result.events_processed})", flush=True)
    print("--- trace (last 20 lines) ---")
    if rt is not None:
        for line in rt.trace.lines()[-20:]:
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
