# Loop Engineering Synthesis: ComPilot + Loop Patterns → Cognitive Runtime

> Research artifact. Synthesizes four independent sources into a single
> architectural map showing how loop engineering primitives map to the
> active-skill-system Cognitive Runtime.

## Sources

1. **ComPilot** (arXiv:2511.00592v2) — LLM-guided compiler optimization via
   feedback loop with Tiramisu compiler. 2.66×–3.54× speedup on PolyBench.
   36% runnable-rate (64% of LLM proposals are illegal).
2. **cobusgreyling/loop-engineering** (784★) — canonical reference for loop
   engineering patterns, primitives, safety levels, CLI tools.
3. **gaasher/Agent-Loop-Skills** — loops-as-skills: program + artifact +
   feedback + ledger + termination. Verification-gated by design.
4. **Forward-Future/loop-library** — catalog + meta-skill for loop discovery.
   "A loop gives the work a clear finish line."

## Core finding

All four sources converge to the **same architectural pattern**:

```
Loop = Program (spec) + Artifact (what's improved) + Feedback (how we score)
     + Termination (when to stop) + State (memory across iterations)
     + Verification Gate (independent check before accept)
```

Our Cognitive Runtime implements **all six components** plus an additional
**anti-fantasy gate** that no source has: a formal prohibition on LLM
self-promoting a claim from PROPOSED to VERIFIED without independent grounding.

## Primitive mapping

### cobusgreyling 6 primitives → our architecture

| Primitive | Our component | Milestone |
|---|---|---|
| 1. Automation / Scheduling | `RunFSM` (16 states: REPAIRING→EXECUTING→VALIDATING) | M003 |
| 2. Worktrees | `ExperimentWorkspace.fork/diff` (SQLite-backed) | M006 |
| 3. Skills | `PromptGenome` (versioned, immutable, with invariants) | M012 |
| 4. Plugins & Connectors (MCP) | `ToolPort` + `ToolRegistry` | M009 |
| 5. Sub-agents (maker/checker) | `ValidateTaskGraphUseCase` (checker) + `RepairLoopUseCase` (maker) | M003/M009 |
| + Memory / State | `TaskGraphBridge` + `ActivegraphEventSink` → event log | M004/M005 |

### gaasher 5 loop ingredients → our architecture

| Ingredient | Our component | Milestone |
|---|---|---|
| Program (`SKILL.md`) | `PromptGenome` (versioned template + slots + invariants) | M012 |
| Artifact slot | `TaskGraph` (versioned, immutable, `GraphPatch`-patchable) | M003/M009 |
| Feedback signal | `ValidateTaskGraphUseCase` + `is_measurable_improvement` | M003/M009 |
| Run ledger | Event log via `ActivegraphEventSink` (append-only, replay) | M005 |
| Termination | `BudgetController` + loop-detection (fingerprint) | M009/M013 |

### ComPilot → our architecture (with improvements)

| ComPilot component | Our equivalent | Improvement over ComPilot |
|---|---|---|
| LLM proposes transformation | `ParseTaskSpecUseCase` → `TaskSpec` | + ModelSelector (per-stage routing, M011) |
| Compiler checks legality | `ValidateTaskGraphUseCase` (pre-check) + Tool | + Pre-validation by dependency graph |
| Feedback: success/fail/speedup | `ToolResult` → `GraphPatch` → `is_measurable_improvement` | + Reject neutral transforms (ComPilot accepts any runnable) |
| Best-of-5 independent runs | `ExperimentWorkspace.fork/diff` | + Shared prefix cache → 40-60% cheaper |
| Static system prompt | `PromptGenome` (M012) | + Versioned, evolvable (D004) |
| No anti-hallucination gate | Anti-fantasy gate (3 layers: Claim/Graph/Output) | + Formal prohibition on self-promotion |
| No budget tracking | `BudgetController` (M013) | + Token/tool/cost tracking + partial on exhaustion |
| No safety levels | `GovernancePolicy` (M002, extensible to L1-L3) | + Graduated autonomy |

## Loop Engineering concepts → our design implications

### Comprehension debt
> Faster loops ship more code you didn't write — comprehension debt grows.

Our anti-fantasy gate directly addresses this: every claim has provenance,
every patch has measurable-improvement evidence, every fork has diff.
The human can **always audit** what happened through the event log (M005 replay).

### Intent debt
> Every session the agent starts cold. Missing intent gets filled with guesses.

Our `PromptGenome` (M012) encodes intent as versioned, immutable specs with
invariants. Skills (`SKILL.md` files) persist project conventions. The agent
reads intent from the genome, not from guesses.

### Safety levels L1-L3
| Level | Loop Engineering | Our equivalent | Component |
|---|---|---|---|
| L1 | Report-only, no auto-action | `ReasoningResult` (no side effects) | M003 |
| L2 | Patch in worktree, human review | `ExperimentWorkspace.fork` → diff → human gate | M006 |
| L3 | Auto-merge for trivial | `GraphPatch.apply` with measurable-improvement gate | M009 |

**Recommendation:** Extend `GovernancePolicy` (M002 domain) with
`safety_level: SafetyLevel` enum (L1/L2/L3). The repair loop checks
the policy before applying patches: L1 = report only, L2 = fork + diff +
wait, L3 = apply if improvement gate passes.

### Maker/checker split
> The agent that wrote the code is a terrible judge of its own work.

Our architecture enforces this structurally:
- **Maker**: `RepairLoopUseCase` proposes GraphPatch
- **Checker**: `ValidateTaskGraphUseCase` independently validates
- **Output gate**: `OutputVerifierUseCase` (M013) does final deterministic check

The LLM **cannot** mark its own work done — that requires an independent
validator (concept.md §8 anti-fantasy rule).

### Attempt cap + kill switch
> Hard cap (e.g. 3 attempts) → escalate with full context in state file.

Our `BudgetController` (M013) enforces `max_cycles` + `max_tool_calls`.
Loop-detection (M009) uses fingerprinting to detect cycles. When budget
is exhausted → `RepairStatus.PARTIAL` with honest gaps.

## ComPilot domain profile — architectural integration

### What changes in our architecture: NOTHING in the core

Adding ComPilot as a domain profile requires:
1. **Domain-specific node/edge types** — extension of NodeKind/EdgeKind enums
   (COMPILER_LOOP, FLOW_DEP, ANTI_DEP, etc.) or domain-specific sub-enum.
2. **ToolPort implementation** — `TiramisuCompilerTool` (compile → measure → ToolResult).
3. **RepairPolicy extension** — gap_class → action mapping for compiler domain
   (DEPENDENCY_VIOLATION → replan, etc.).
4. **PromptGenome for compiler** — system prompt for loop optimization agent.

**What does NOT change:**
- TaskGraph (M003) — generic reasoning structure
- ValidateTaskGraphUseCase (M003) — generic validator
- RepairLoopUseCase (M009) — generic bounded loop
- ExperimentWorkspace (M006) — generic fork/diff
- BudgetController (M013) — generic budget enforcement
- ModelSelector (M011) — generic per-stage routing
- Event log / replay (M004/M005) — generic audit trail

### Expected improvements over vanilla ComPilot

| Metric | ComPilot vanilla | Our approach (estimated) | Mechanism |
|---|---|---|---|
| Runnable-rate | 36% | 60-80% | Pre-validation by dependency graph (RepairPolicy constrains action space) |
| Cumulative tokens | baseline | -20-40% | Fewer illegal proposals → fewer wasted LLM calls |
| Speedup quality | 2.66× (1 run) | ≥90% of vanilla | Measurable-improvement gate doesn't reject good transforms |
| Best-of-N cost | 5× full dialogues | 2-3× tokens | Fork/diff shared prefix cache (ExperimentWorkspace) |
| Wall-clock per instance | baseline | -30% | ModelSelector (fast model for parse) + fewer cycles |

## Practical applications (one runtime, multiple domains)

| Domain | What's optimized | Feedback signal | Tool |
|---|---|---|---|
| Compiler optimization (ComPilot) | Loop transforms | Compile + speedup | TiramisuCompilerTool |
| Code quality (loop-engineering) | Code changes | Tests + lint + review | CodeValidatorTool |
| ML hyperparameters (gaasher) | Model config | Training metric (val_acc) | TrainingRunTool |
| Research answers (our M007) | Claims + evidence | Citation coverage | SearchTool |
| Database queries | Query plan | Execution time | QueryPlanTool |
| Infrastructure config | K8s/Terraform | Cost + latency + validation | ConfigValidatorTool |
| Security hardening | Security rules | SAST findings | SASTScannerTool |

**Architecture invariant:** the Cognitive Runtime core (TaskGraph, RepairLoop,
BudgetController, ExperimentWorkspace, Anti-fantasy gate) is **unchanged**
across all domains. Only the domain profile (node types, tool, policy, prompt)
changes.

## Roadmap implications

1. **D006**: Loop Engineering Synthesis — recorded (this decision).
2. **Research doc**: this file (`doc/loop-engineering-synthesis.md`).
3. **GovernancePolicy extension**: add `safety_level: SafetyLevel` (L1/L2/L3).
4. **ComPilot domain profile (M014+)**: after P0 closure (F-13/F-14).
5. **Experience Store (concept M5)**: enables Variant B (RLM search) —
   caching (subgraph, transform) → (speedup, success) for sample-efficiency.
6. **Evolvable trait extraction (D004)**: ComPilot TransformationTemplate
   = third concrete Evolvable case → trait extraction ready.

## References

- ComPilot: arXiv:2511.00592v2, DOI 10.5281/zenodo.16812384
- Loop Engineering: github.com/cobusgreyling/loop-engineering (784★)
- Agent-Loop-Skills: github.com/gaasher/Agent-Loop-Skills
- Loop Library: github.com/Forward-Future/loop-library
- Addy Osmani, "Loop Engineering" (blog post)
- Peter Steinberger: "You shouldn't be prompting coding agents anymore."
