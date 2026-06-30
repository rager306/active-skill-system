"""L4 Composition — sandbox runs (M052 S00).

Action modes that invoke LLM: --model, --models, --check, --bench.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from active_skill_system.composition.cli_exit import EX_NOT_FOUND, EX_OK, EX_PARTIAL
from active_skill_system.composition.sandbox.helpers import get_sandbox_logger


def build_executor(executor_type: str) -> Any:
    """Build a CodeExecutorPort adapter by type string (lazy import, R008)."""
    if executor_type == "bwrap":
        from active_skill_system.adapters.bwrap_executor import BwrapExecutor
        return BwrapExecutor()
    from active_skill_system.adapters.inprocess_executor import InProcessExecutor
    return InProcessExecutor()


def write_ratchet_entry(ratchet_path: str, result: Any) -> None:
    """Write a permanent ratchet entry for a failed sandbox run (D012 dogfood)."""
    from harness import RatchetEntry, RatchetLedger

    error_detail = result.error or f"fitness={result.fitness.score:.2f}"
    axes = result.fitness.axes()
    failed_axes = [k for k, v in axes.items() if isinstance(v, bool) and not v and k != "score"]
    entry = RatchetEntry.new(
        area="sandbox",
        diff=f"model={result.model} score={result.fitness.score:.2f} failed_axes={failed_axes}",
        justification=f"Sandbox run failed: {error_detail}",
        test_ref=result.generated_path or "unknown",
    )
    ledger = RatchetLedger.load(Path(ratchet_path))
    ledger.append(entry)
    print(f"ratchet: entry written to {ratchet_path} ({entry.id})", flush=True)


def run_check(candidate_path: str) -> int:
    """Score a candidate module deterministically (no LLM)."""
    from active_skill_system.application.use_cases.sandbox_verifier import verify_candidate

    fitness = verify_candidate(candidate_path)
    axes = fitness.axes()
    print(f"candidate: {candidate_path}", flush=True)
    print(f"score: {axes['score']:.2f}", flush=True)
    for name, val in axes.items():
        if name != "score":
            print(f"  {name}: {val}", flush=True)
    return EX_OK if axes["score"] == 1.0 else EX_PARTIAL


def run_single_model(
    model: str, executor_type: str = "inprocess",
    graph_path: str = "runs/sandbox_graph.lbdb",
    ratchet_path: str | None = None,
    strategy: str = "plain",
    event_store: Any = None,
) -> int:
    """Run one model on the benchmark; record Loop + LoopGraph provenance."""
    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore
    from active_skill_system.adapters.llm.minimax import MiniMaxProvider
    from active_skill_system.adapters.plain_llm_strategy import PlainLLMStrategy
    from active_skill_system.application.use_cases.sandbox_agent_runner import SandboxAgentRunner
    from active_skill_system.domain.loop_graph import LoopEdgeKind, project

    if strategy == "dspy":
        from active_skill_system.adapters.dspy_strategy import DSPyStrategy

        engine = DSPyStrategy()
        if engine.is_stub:
            print(f"dspy_strategy: stub mode ({engine.stub_reason}); falling back to plain", flush=True)
            engine = PlainLLMStrategy(provider=MiniMaxProvider())
        else:
            print(f"dspy_strategy: configured (model={engine._dspy_lm.model})", flush=True)
    elif strategy == "fast-rlm":
        from active_skill_system.adapters.fast_rlm_strategy import FastRLMStrategy

        engine = FastRLMStrategy()
        if engine.is_stub:
            print(f"fast_rlm_strategy: stub mode ({engine.stub_reason}); falling back to plain", flush=True)
            engine = PlainLLMStrategy(provider=MiniMaxProvider())
        else:
            print(f"fast_rlm_strategy: configured (primary={engine._resolved_primary})", flush=True)
    else:
        engine = PlainLLMStrategy(provider=MiniMaxProvider())
    code_executor = build_executor(executor_type)
    runner = SandboxAgentRunner(engine=engine, code_executor=code_executor)
    result = runner.run(model=model)

    store = LadybugGraphStore(graph_path)
    graph = project(result.loop, trajectory=result.trajectory)
    store.store_loop_graph(graph)

    get_sandbox_logger().info(
        "run_complete run_id=%s model=%s score=%.2f trajectory_steps=%d generated=%s error=%s",
        result.loop.id, result.model, result.fitness.score,
        len(result.trajectory), result.generated_path or "none", result.error or "none",
    )

    if event_store is not None and result.trajectory:
        from active_skill_system.application.use_cases.emit_trajectory_events import (
            emit_trajectory_events,
        )

        n = emit_trajectory_events(
            steps=result.trajectory, store=event_store, run_id=result.loop.id,
        )
        print(f"event-log: emitted {n} events for {result.loop.id}", flush=True)

    print(f"model: {result.model}", flush=True)
    print(f"loop: {result.loop.id} state={result.loop.state.value}", flush=True)
    print(f"score: {result.fitness.score:.2f}", flush=True)
    axes = result.fitness.axes()
    for name, val in axes.items():
        if name != "score":
            print(f"  {name}: {val}", flush=True)
    if result.error:
        print(f"error: {result.error}", flush=True)
    if result.generated_path:
        print(f"generated: {result.generated_path}", flush=True)
    loop_vid = f"loop:{result.loop.id}"
    neighbours = store.query_neighbours(loop_vid, direction="out")
    print(f"provenance: {len(graph.vertices)} vertices, {len(graph.edges)} edges", flush=True)
    print(f"  {loop_vid} -> {[v.id for v in neighbours]}", flush=True)
    verified = store.has_edge(LoopEdgeKind.VERIFIED_BY, loop_vid, "verifier:sandbox-verifier")
    print(f"  VERIFIED_BY verifier: {verified}", flush=True)

    if ratchet_path and (result.fitness.score < 1.0 or result.error):
        write_ratchet_entry(ratchet_path, result)

    return EX_OK if result.fitness.score == 1.0 else EX_PARTIAL


def run_multi_model(models_csv: str, graph_path: str = "runs/sandbox_graph.lbdb") -> int:
    """Run the benchmark across N models; print comparative report."""
    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore
    from active_skill_system.adapters.llm.minimax import MiniMaxProvider
    from active_skill_system.adapters.plain_llm_strategy import PlainLLMStrategy
    from active_skill_system.application.use_cases.sandbox_harness import SandboxHarness
    from active_skill_system.domain.loop_graph import project

    models = [m.strip() for m in models_csv.split(",") if m.strip()]
    engine = PlainLLMStrategy(provider=MiniMaxProvider())
    harness = SandboxHarness(engine=engine, models=models)
    report = harness.run_all()

    store = LadybugGraphStore(graph_path)
    _ = (project, store)

    print(report.table(), flush=True)
    return EX_OK if report.winner_score == 1.0 else EX_PARTIAL


def run_program_bench(
    model: str, executor_type: str, graph_path: str, ratchet_path: str | None, strategy: str,
) -> int:
    """ProgramBench smallest-CLI validator (M053 S01, D014)."""
    import subprocess
    import sys
    import uuid

    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore
    from active_skill_system.adapters.llm.minimax import MiniMaxProvider
    from active_skill_system.adapters.plain_llm_strategy import PlainLLMStrategy
    from active_skill_system.application.ports.reasoning_engine import ReasoningRequest
    from active_skill_system.domain.loop_graph import project

    fixture_root = Path("tests/fixtures/program_bench/smallest_cli")
    target = fixture_root / "json_pretty.py"
    parity_tests = fixture_root / "tests" / "test_json_pretty_parity.py"
    if not target.exists() or not parity_tests.exists():
        print(f"program_bench: fixture missing at {fixture_root}", flush=True)
        return EX_NOT_FOUND

    spec = (
        "Write a Python CLI named 'json_pretty' that pretty-prints JSON. "
        "Requirements: (1) read JSON from a file path argument or stdin if no path "
        "is given, (2) --indent N sets indent width (default 2), (3) --sort-keys sorts "
        "object keys alphabetically (off by default), (4) --indent 0 produces compact "
        "output (no whitespace), (5) exit 0 on success, exit 1 with a stderr message "
        "on invalid JSON. Use only the Python standard library. Output only the code."
    )

    if strategy == "dspy":
        from active_skill_system.adapters.dspy_strategy import DSPyStrategy
        engine = DSPyStrategy()
    elif strategy == "fast-rlm":
        from active_skill_system.adapters.fast_rlm_strategy import FastRLMStrategy
        engine = FastRLMStrategy()
    else:
        engine = PlainLLMStrategy(provider=MiniMaxProvider())

    request = ReasoningRequest(
        system="You are a Python code generator. Output only code.",
        prompt=spec, model=model, max_tokens=16384, temperature=0.0,
    )
    response = engine.forward(request)
    if response.error:
        print(f"program_bench: reasoning failed: {response.error}", flush=True)
        return EX_PARTIAL
    raw = response.text or ""
    from active_skill_system.application.use_cases.sandbox_agent_runner import _extract_code
    code = _extract_code(raw)
    if not code.strip():
        print("program_bench: empty candidate", flush=True)
        return EX_PARTIAL

    run_id = f"program-bench-{uuid.uuid4().hex[:8]}"
    out_dir = Path("runs/program_bench") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate = out_dir / "json_pretty.py"
    candidate.write_text(code, encoding="utf-8")
    print(f"program_bench: candidate written to {candidate}", flush=True)

    parity_runner = out_dir / "test_parity.py"
    runner_src = parity_tests.read_text(encoding="utf-8")
    runner_src = runner_src.replace(
        "_FIXTURE_DIR = Path(__file__).resolve().parents[1]",
        f"_FIXTURE_DIR = Path({str(candidate)!r}).parent",
    )
    parity_runner.write_text(runner_src, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(parity_runner), "-q", "-p", "no:cacheprovider"],
        capture_output=True, text=True, timeout=60,
    )
    print(proc.stdout, flush=True)
    if proc.returncode != 0:
        print(proc.stderr, flush=True)
        return EX_PARTIAL

    from active_skill_system.domain.loop import Budget, Loop, LoopEvent, LoopEventKind, LoopState

    loop = Loop.start(
        id=run_id, intent=f"program-bench:{model}",
        budget=Budget(max_llm_calls=1, max_cost=0.05), skills=("program-bench",),
    )
    loop = loop.advance(LoopEvent.now(LoopEventKind.VERIFIED, LoopState.VERIFYING, {"verifier": "program-bench-parity"}))
    loop = loop.advance(LoopEvent.now(LoopEventKind.FINISHED, LoopState.DONE, {"score": 1.0}))
    store = LadybugGraphStore(graph_path)
    store.store_loop_graph(project(loop))

    get_sandbox_logger().info("program_bench_passed run_id=%s model=%s score=1.0", run_id, model)
    return EX_OK
