# ROADMAP — active-skill-system

> Living document. Updated 2026-06-30 after Waves A/B/C/D completion.
> Source of truth for milestone sequencing and wave status.

## Wave Structure

```
✅ COMPLETE                    ⏭️ NEXT                       🔲 FUTURE
```

### ✅ Foundation (M001-M045) — COMPLETE

The disciplined hexagonal core + evolution engine + RGLA provenance.

| Milestone | What | Key outcome |
|-----------|------|-------------|
| M001-M010 | Architecture synthesis, domain filling, genome foundation | Hexagonal layers enforced, 3 genomes (Model/Prompt/Code) |
| M011-M015 | ModelGenome, PromptGenome, per-stage selection | Evolvable trait proven |
| M016-M023 | Compiler/SQL/IaC/Network/Storage/Log/ML/Security domains | MEM019 pattern: 8 domain profiles |
| M024-M035 | Multi-stage evolution, weighted fitness, evidence ledger, idempotency | MultiEvolvableEngine |
| M036-M045 | LoopGraph, sandbox verifier, budget, riskratchet, mutation testing | 11-axis verifier, R010/R011 gates |

### ✅ Wave 1-4 (M047-M050) — Sandbox Foundation COMPLETE

| Milestone | Wave | What | Tests |
|-----------|------|------|-------|
| M047 | P0 | Disk persistence + graph queries + ratchet dogfood | REAL-LLM: 2 runs → 6 vertices |
| M048 | P1 | Trajectory logging + env-based paths | REAL-LLM: 16 trajectory steps |
| M049 | P2 | Insight & Feedback Loop (--report/--compare-runs/--recommend) | 14-fact report |
| M050 | P3 | Reasoning Expansion (DSPy + FastRLM + ProgramBench) | dspy score 1.00, 9/9 parity |

### ✅ Wave A (M051) — Port Split COMPLETE

**Solved the LadybugDB lock-in.** GraphBackend (generic Vertex/Edge) + EventStore (semantic GraphEvent) + EventLogBackend (raw SQLite/Postgres/in-memory). Adding HelixDB = one adapter file.

### ✅ Recursive Dogfooding — COMPLETE

`--governance-check` (8 axes) + GSD PreVerify hook. The project validates ITSELF with its own tools. Governance 100%.

### ✅ Wave B (M052) — Trace + Fork-Diff + LLMCache + Async COMPLETE

Distributed trace foundation (TraceEnvelope + TraceCollector). ForkEngine (branch at any event). LLMCache (zero-cost prefix). AsyncForkEngine (first async code, D019). --fork/--diff CLI modes.

### ✅ Wave C (M053) — Reactive Runtime COMPLETE

Absorbed activegraph primitives #3 (Behaviors), #5 (Patches), #8 (Policies), #9 (Patterns). BehaviorRuntime fires behaviors on events. PatchApplier lifecycle. PolicyGate (4 rules). PatternMatcher (graph-shape triggers). EventEmitting wrappers audit all operations. 3 preset behaviors.

### ✅ Wave D (M054) — ActiveGraph Absorption COMPLETE

All 12 activegraph primitives covered. Added #4 (Relations), #6 (Views), #7 (Frames), #10 (Replay). ReactiveSandboxAgentRunner: reactive during REAL agent runs (not just demo). ForkReplayCacheEngine: fork+replay+cache killer feature. Diligence behavior pack. LLMRouter M038 gap closed. ForkAnalysis: WHY forks diverge.

## Current State (2026-06-30)

```
Milestones:    54 completed (M001-M054)
Tests:         1838 passed, 9 skipped
Layering:      KEPT (2 contracts, 0 broken)
Governance:    100% (8/8 axes OK)
Ports:         13 (all swap-able)
Genomes:       5 evolvable (Model/Prompt/Transformation/SQL/IaC)
FSMs:          2 (RunFSM 16-state cognitive + LoopFSM 6-state operational)
Primitives:    12/12 activegraph covered
Decisions:     21 (D001-D021)
Requirements:  20 (13 validated, 5 active, 2 new)
Async:         present (AsyncForkEngine, D019 first seam)
Reactive:      production-ready (works during real LLM runs)
```

## ⏭️ Wave E (M055) — Maxi Scaling — NEXT

The north-star track: grow from MINI (isolated sandbox) to MAXI (comprehensive SDLC harness).

| Slice | What | Priority |
|-------|------|----------|
| S01 | Multi-domain benchmark suite (run all 5 genomes in one pipeline) | high |
| S02 | Golden Sessions (record + replay canonical agent sessions for regression) | high |
| S03 | Reactive composition wiring into diligence.py (currently uses hardcoded provider) | medium |
| S04 | Real-LLM reactive E2E (S11 marked test → actual --runllm validation) | medium |
| S05 | LLMRouter wired into mini_sandbox --strategy router | low |
| S06 | Streaming LLM responses (async upgrade, token-by-token) | future |
| S07 | Pattern subscriptions temporal (NOT EXISTS → EXISTS with time conditions) | future |
| S08 | HelixDB GraphBackend adapter (validate swap-ability) | low |
| S09 | Postgres EventLogBackend adapter | low |
| S10 | R013 automation (risk delta in GSD SUMMARY.md) | medium |

## 🔲 Future Tracks

### Post-Wave E

- **Golden Session replay** — canonical agent sessions as regression baselines
- **Cross-domain genome transfer** — learned improvements transfer between domains
- **Multi-agent orchestration** — multiple loops cooperating via EventStore
- **Real-time dashboard** — live trace + event + reactive visualization
- **Distributed execution** — multi-process reactive runtime (beyond single-process asyncio)

## Architectural Principles (enduring)

1. **Hexagonal layers** — inward-only dependencies, enforced structurally (R001/R007)
2. **Ports are swap seams** — 13 ports, adding a backend = one adapter file
3. **Domain is pure** — stdlib only, frozen dataclasses, no I/O (R002/R003)
4. **Evolution is generic** — one engine, 5 genomes, MEM019 pattern reusable
5. **Reactive is production-ready** — events trigger behaviors during real runs
6. **Observability is layered** — EventStore (WHAT) + TraceCollector (WHY) + Trajectory (HOW)
7. **Self-governance** — recursive dogfooding, 8 axes, 100%
8. **Phased async** — D019: no retroactive async-ification, asyncio.to_thread bridges
