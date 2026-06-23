"""L4 composition root — run the Diligence pack against MiniMax.

Wires the MiniMax adapter (L3) into the ActiveGraph runtime and runs the
Diligence pack for one company. The goal MUST start with "Diligence:" (the
company_planner guard) or the reasoning cascade never fires.

Usage:
    uv run active-skill-diligence [company]
    .venv/bin/python -m active_skill_system.composition.diligence [company]

Known limitation: tool-driven behaviors (document_researcher, memo_synthesizer)
hit MiniMax error 2013 until the thinking-preservation shim lands — see the
`activegraph` skill / findings gap 5.1.
"""

from __future__ import annotations

import sys

from activegraph import Graph, Runtime, configure_logging

from active_skill_system.adapters.llm.minimax import MiniMaxProvider, load_env

configure_logging(level="ERROR", json_output=False)


def main(argv: list[str] | None = None) -> int:
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

    from activegraph.packs.diligence import DiligenceSettings
    from activegraph.packs.diligence import pack as diligence_pack

    graph = Graph()
    rt = Runtime(
        graph,
        llm_provider=MiniMaxProvider(),
        persist_to="diligence_run.db",
        budget={"max_llm_calls": 40, "max_tool_calls": 60, "max_cost_usd": "2.00"},
        seed=0,
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

    print(f"running Diligence on '{company}' with {model} ...", flush=True)
    rt.run_goal(f"Diligence: {company}")
    rt.save_state()
    print("RUN OK", flush=True)
    print("--- trace (last 20 lines) ---")
    for line in rt.trace.lines()[-20:]:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
