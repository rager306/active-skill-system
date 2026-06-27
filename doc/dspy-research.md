# DSPy integration — research note (deep)

> Status: **research / integration evaluation**. DSPy evaluated across its FULL
> ecosystem, not just teleprompters. NOT adopted yet — no code.
> Companion to the mini-loop (D013) and the RGLA vision.
>
> Source: dspy.ai docs (verified 2026-06 via get_library_docs `/websites/dspy_ai`).

## 1. DSPy is a full LLM-programming framework, not just a prompt optimizer

The initial note focused on BootstrapFewShot/MIPRO. That undersold DSPy badly.
DSPy is a **competing framework** for what we are building — it spans:

| DSPy layer | What it does | Our analogue | Relationship |
|------------|--------------|--------------|--------------|
| **Signatures** | Declarative input→output contracts | `Evolvable` genome spec | Overlap — both declare contracts |
| **Modules** (`Predict`, `ChainOfThought`, `ReAct`, `ProgramOfThought`, `MultiChainComparison`) | Composable LLM programs (reasoning/tool/code-exec patterns) | `RunReasoningUseCase`, runtime FSM | **Strong overlap** — DSPy modules = our use-cases, pre-packaged |
| **ReAct** | Reasoning + tool loop with trajectory + truncation | `RuntimePort` tool loop | Near-identical; DSPy's is standalone, ours is layered |
| **ProgramOfThought** | Generate→execute→regenerate Python code loop | `SandboxAgentRunner` (M042) | DSPy has this built-in (our sandbox is a custom version) |
| **Teleprompters** (`BootstrapFewShot`, `BootstrapFewShotWithRandomSearch`, `MIPROv2`, `COPRO`, `KNNFewShot`) | Compile prompts: demo bootstrapping + instruction tuning | `EvolutionEngine` + `PromptGenome` (M012) | Complementary — DSPy = specialised prompt compiler; our engine = generic genome mutator |
| **GEPA** (Genetic-Pareto) | Reflective prompt evolution: scalar score + textual feedback → proposes new instructions via reflection LM; Pareto candidate selection | `EvolutionEngine` (structural mutation) | **Direct competitor** to our evolution approach — GEPA is LLM-reflection-driven; ours is structural |
| **Assertions/Suggest** | Constraint-based verification with retry | `VerifiedToolResult` + anti-fancy gate (M014/D007) | Overlap — both enforce contracts; DSPy's is per-call retry, ours is evidence-ledger |
| **Evaluate** | Batch evaluation with metrics + threads | `SandboxHarness` multi-model (M042 S03) | Overlap — DSPy's is more mature |
| **Retrieve** | Retrieval modules | (not built; Context Graph §9 Q3) | DSPy could supply this layer |
| **Tools / MCP** | Tool-use + MCP integration | `ToolRegistry` + `ToolPort` | Overlap |
| **Fine-tuning** | LoRA fine-tuner (MIPRO+LoRA) | (not in scope) | Orthogonal |

## 2. The honest question: competitor, complement, or substrate?

DSPy is **not** just a prompt-optimizer to bolt onto PromptGenome. Three honest
stances:

### Stance A — Competitor (replace)
DSPy already provides Modules (reasoning/tool/code-exec), Assertions (verify),
Optimizers (GEPA/Bootstrap/MIPRO), Evaluate. Much of what we hand-built
(EvolutionEngine, SandboxAgentRunner, multi-model harness) exists in DSPy in a
more mature form. We *could* adopt DSPy as the substrate and reduce our custom
code.

**Risk:** vendor lock-in to DSPy's abstractions; our layered architecture (R002)
becomes a wrapper around DSPy; we lose the RGLA-specific design (Loop/LoopGraph
provenance, typed sub-Loop contracts D011).

### Stance B — Complement (plug in for one capability)
Use DSPy for **one** thing it does better than us, behind a port. Strongest
candidates:
  - **GEPA** as an EvolutionEngine mutation strategy (LLM-reflection-driven
    instruction evolution vs our structural mutation).
  - **BootstrapFewShot** for automatic demo collection on PromptGenome.

**Advantage:** keeps our architecture (R002, RGLA provenance); DSPy is one L3
adapter. This is the safest integration.

### Stance C — Substrate (build on DSPy)
Adopt DSPy Modules as the reasoning layer, our RGLA as the provenance/evolution
layer on top. DSPy handles reasoning (CoT/ReAct/PoT), we handle Loop lifecycle +
LoopGraph + typed contracts.

**Risk:** deepest integration; highest coupling; but potentially the most
powerful — DSPy's mature modules + our provenance/evolution.

## 3. What DSPy's ecosystem has that we genuinely lack

1. **GEPA** — reflective prompt evolution with textual feedback. Our
   EvolutionEngine mutates structurally; GEPA uses a reflection LM to *propose*
   improvements from failure feedback. This is a fundamentally different and
   powerful mutation strategy we do not have.
2. **ProgramOfThought** — generate→execute→regenerate loop with built-in code
   execution + error feedback. Our SandboxAgentRunner is a simpler version.
3. **MIPROv2** — joint instruction + demo optimization. We have neither.
4. **BootstrapFewShotWithRandomSearch** — robust demo selection. We hand-write.
5. **Assertions/Suggest** — declarative constraint verification with automatic
   retry. Our VerifiedToolResult is manual.

## 4. Recommended integration path (revised from the first note)

Do NOT start with "BootstrapFewShot for PromptGenome" (too narrow). Start with
**GEPA as an EvolutionEngine strategy**, because GEPA is the most different from
what we have and the most relevant to our evolution vision:

```
Our EvolutionEngine
  ↓ one mutation operator =
GEPA (reflection LM proposes new instructions from fitness feedback)
  ↓ applied to
PromptGenome (M012) on the sandbox benchmark
  ↓ compared against
structural mutation (current default)
```

This proves the composition: GEPA ⊂ EvolutionEngine, behind a port (R002).

### Layering
```
application/ports/prompt_optimizer.py    ← PromptOptimizer Protocol
adapters/dspy_gepa_optimizer.py          ← GEPA-backed optimizer (L3)
adapters/dspy_bootstrap_optimizer.py     ← (future) BootstrapFewShot
composition/...                           ← wires the adapter
```

### Training set
5–8 small domain-type benchmarks (variations of MEM019). GEPA's
`reflection_minibatch_size=3` means it reflects on 3 examples per mutation —
needs variety.

## 5. Honest risks (expanded)

1. **Heavy dependency** (~67 packages). Optional-dependency `[dspy]`; port-gated.
2. **GEPA needs a reflection LM** (separate from the student LM) — cost + a
   second model. Docs recommend a strong reflection model (gpt-5-class).
3. **Determinism** — GEPA + Bootstrap are LLM-driven (stochastic). Our verifier
   stays deterministic; the optimization loop is not.
4. **Overlap is real** — if we adopt too much DSPy, we become a wrapper. The
   boundary (R002 port + RGLA provenance as the differentiator) must hold.
5. **ProgramOfThought overlap** — our SandboxAgentRunner is a custom PoT. If we
   adopt DSPy PoT, we'd deprecate part of S02. Decide consciously, not by drift.

## 6. Open questions (resolve before build)

1. **Stance**: B (complement, GEPA only) or C (substrate, DSPy modules as
   reasoning layer)? This is the biggest fork.
2. **GEPA reflection model**: which model? The proxy has gpt-5-class? Or use
   MiniMax-M3 as both student and reflection?
3. **Training set**: 5–8 hand-authored domain-types, or generate them from the
   12 existing profiles?
4. **Deprecation**: if DSPy ProgramOfThought replaces SandboxAgentRunner, is
   that acceptable? Or keep both (SandboxAgentRunner for determinism, DSPy PoT
   for optimised runs)?
