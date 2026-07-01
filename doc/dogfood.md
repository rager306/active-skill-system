# Dogfooding the architecture — applying RGLA to our own dev process

> Status: **DELIVERED** ✅. Implemented as `--governance-check` (8 axes) +
> GSD PreVerify hook (scripts/hooks/pre-verify.sh). The project validates
> ITSELF with its own verification tools. Governance score 100%.
> Companion to D012. Originally a design/stance doc; now production code.
>
> Decision: D012. Inputs: the 4 real-LLM bugs (MEM044-046), the empty
> RatchetLedger (M033), the RGLA build (M041).

## 1. The thesis

The project built a machine for evolving skills and learning from loops — but
applies it only to foreign domains (compiler/SQL/IaC stubs). Its own
dev-process bugs evaporate. Real-LLM testing just found **4 bugs** that **1239
offline tests never saw**, and none became a permanent improvement. The
RatchetLedger implementation is complete (M033, 34 tests) but the ledger file
is **empty**.

Dogfooding closes that gap: apply the project's own Loop / Ratchet / LoopGraph
/ Evolution to its own development, on one scoped loop, never the whole process
at once.

## 2. What is already built and ready to apply to ourselves

| Element | Built | Applied to ourselves? |
|---------|-------|-----------------------|
| Loop domain (D009, M041) | ✅ `domain/loop.py` | ❌ — never instantiated for a dev task |
| LoopGraph provenance (M041) | ✅ `domain/loop_graph.py` + `project()` | ❌ |
| GraphStore / LadybugGraphStore (D010, M041) | ✅ real Cypher store | ❌ |
| RatchetLedger (M033) | ✅ `harness/__init__.py`, 34 tests | ❌ **ledger file is EMPTY** |
| Typed errors (M040) | ✅ ToolError/LLMUnavailable/… | ✅ (used in real bugs) |
| Logging backbone (M040) | ✅ loguru intercept + LOG_DIR | ✅ |
| Evolution Engine (M011-M029) | ✅ generic Evolvable | ❌ (foreign domains only) |
| Golden Sessions (D011) | ⏳ deferred | ❌ |

The paradox D012 addresses: a machine for learning from loops whose own lessons
are discarded.

## 3. The first loop (sandbox-observed, NOT touching live code)

**Refinement (D012):** dogfood runs in an ISOLATED sandbox workspace — an
observer, not a participant in the live dev process. The sandbox runs one
SDLC benchmark many times across models/strategies and collects fitness +
LoopGraph provenance; the main codebase is never modified by it. This removes
the velocity risk of wrapping the dev process itself in Loops.

### 3.1 The benchmark: a feature-slice (MEM019 pattern)

The first SDLC benchmark is a **feature-slice**: implement one domain-type +
tests (the exact MEM019 template the project has repeated 12 times: frozen
dataclass + StrEnum + better_than ranking + primary fitness axis). Fitness is
objective and fast:
  - `tests pass / fail` (binary)
  - layering KEPT (import-linter, R002)
  - ruff clean
  - LOC under R006 (≤200)

This is deliberately a familiar task: the project KNOWS the answer, so the
sandbox measures **how an agent+model arrives at it**, not whether the task is
solvable. That makes fitness comparable across models and iterations.

### 3.2 The loop

```
(one SDLC benchmark: implement cache_types.py + tests)
   ▼  run N times, each with a different model (minimax/glm/gemini/kiro)
Loop(PENDING → RUNNING → VERIFYING → DONE)        ← domain/loop.py
   ▼
fitness signal per run: tests_pass, layering, loc, cost, latency
   ▼
LoopGraph provenance per run                       ← domain/loop_graph.project()
   run ──USES──> skill ──VERIFIED_BY──> test-suite
   ▼
ratchet/ledger.jsonl: permanent model-strategy lessons
   ▼
reader query: "which model produced the cleanest feature-slice for this
                benchmark, and which strategy mutated toward it?"
```

### 3.3 What the sandbox observes (the actual signal)

- **Multi-model experience** — minimax vs glm vs gemini vs kiro on the SAME
  benchmark → comparable fitness. Data the project does not have today.
- **Evolution over iterations** — does a strategy's fitness improve across
  runs? which mutation operators help? LoopGraph shows the trajectory.
- **Agent cooperation patterns** — when a run uses sub-agents (RLM, D011), how
  do typed sub-Loop contracts (D011 §5.3) route evidence?
- **Shared memory pressure** — does the LoopGraph / ratchet actually answer the
  reader query, or is it noise? (This validates the architecture on itself.)

### 3.4 What stays deferred

- Bug→ratchet loop: the 4 real-LLM bugs (MEM044-046) remain available as a
  future seed, but the first loop is feature-slice (objective fitness, many
  iterations, comparable across models).
- Fat-skill evolution, Golden Sessions: gated on D011/D012 revisit criteria.

## 4. Discipline / anti-over-engineering (D012 §4)

1. **A dogfood Loop covers a REPEATED pain, not every task.** Wrapping each
   milestone/task in a Loop kills velocity. Start with the bug→fix loop only.
2. **Provenance edges must have a concrete reader.** A LoopGraph that nobody
   queries is noise. The first loop must answer a real question: *"which fix
   repaired a similar bug before?"*
3. **Do NOT duplicate GSD.** GSD owns milestone/slice/task state and its
   activity journal (`.gsd/activity/*.jsonl`). The dogfood loop owns
   **bug → fix → permanent-knowledge** provenance and *feeds* GSD; it does not
   replace it.

## 5. Boundary with GSD (the dual-ledger rule)

```
GSD (.gsd/)              : workflow state — milestones, slices, tasks, ROADMAP,
                           summaries, activity journal. System-managed.
dogfood (ratchet/ +      : permanent dev-knowledge — bug→fix→ratchet entries +
         LoopGraph via       LoopGraph provenance edges. The thing an agent
         GraphStore)         queries to avoid repeating a fixed bug.
```

A bug found during a GSD task → a ratchet entry (dogfood) + a GSD task SUMMARY
(GSD). Different readers, different stores, no duplication.

## 6. What is explicitly deferred (behind revisit criteria)

| Deferred | Revisit when |
|----------|--------------|
| Fat-skill evolution (ratchet entries → `.agents/skills/*/SKILL.md` by regression-rate fitness) | Enough ratchet entries exist to justify it AND the first loop's query is run |
| Golden Sessions compiler (D011) | Its own D011 criterion |
| Wrapping every dev task in a Loop | Never by default; only repeated, patterned work |

## 7. Why the first loop is itself a real-LLM/real-instrument test of the architecture

Applying LoopGraph to our own bugs will surface where Loop / LoopGraph /
Ratchet are inconvenient or incomplete — exactly as applying real-LLM tests
surfaced the MiniMax `recognizes_model` bug. Expected findings (to validate,
not assume):
- Can `project()` represent a *recurring* bug pattern (same root cause, many
  symptoms)? If not, LoopGraph needs a `PATTERN_OF` edge.
- Is a ratchet entry rich enough to answer "is this bug a recurrence of an
  earlier one?" If not, entries need a fingerprint/similarity field.
- Does the GSD↔dogfood boundary hold in practice, or does state leak?

These are the dogfood's deliverables, not pre-decided answers.

## 8. Net effect on the project

- **Real dogfood proof** of D009/D010/D011/D012 — the architecture serves its
  own builder, not only foreign stubs.
- **Bug→knowledge pipeline** — bugs stop evaporating; each becomes permanent.
- **Fitness signal for fat-skills** from real data, not hand-edits.
- **Architecture pressure-test** — applying RGLA to itself finds RGLA's own
  gaps, the same way real-LLM testing found the provider's.
