# fast-rlm — RLM reference-implementation research

> Status: **research / pattern reference**. fast-rlm is studied for transferable
> patterns; it is NOT adopted as a dependency. Companion to `doc/rgla.md` §10.6.
> Decisions it informs: D009 (RGLA scope), D011 (RLM stance).
>
> Source: https://github.com/avbiswas/fast-rlm · PyPI `fast-rlm` · studied 2026-06.

## 1. What fast-rlm is

`fast-rlm` (avbiswas, ~438★ at time of study) is a minimal, installable
implementation of **Recursive Language Models** (arXiv:2512.24601). Its
one-line definition, from its own README:

> "An inference technique where an LLM interacts with arbitrarily long prompts
> through an external REPL. The LLM can write code to explore, decompose, and
> transform the prompt. It can recursively invoke sub-agents to complete smaller
> subtasks. Crucially, sub-agent responses are not automatically loaded into the
> parent agent's context — they are returned as symbols or variables inside the
> parent's REPL."

That last sentence is the crux: it is what gives RLM the infinite-context /
arbitrarily-long-prompt property that RAG and plain LLMs lack.

## 2. How it realises the RLM rubric

| Rubric gate | fast-rlm realisation |
|-------------|----------------------|
| Executable env | Sandboxed REPL via **Deno + Pyodide** (JS/Python); model-written code executes there |
| Prompt externalised | The prompt is a variable in the REPL; never loaded whole into the context window |
| Code calls model | The REPL can call `llm_query(...)` (and spawn sub-agents) |
| Model picks decomposition | The model decides how to chunk/search/filter the prompt and when to recurse |
| State stays symbolic | Sub-agent results are returned as symbols/variables, not streamed into context |

## 3. Transferable patterns → this project

### 3.1 Budget guardrails validate D009

fast-rlm ships exactly the recursion bounds D009 demands as REQUIRED:

- `--max-depth` (recursion depth)
- `--max-calls` (per-agent call budget)
- `--max-global-calls` (whole-run call budget)

This is concrete evidence that "Loop never ends" is an anti-pattern in practice
— real RLM implementations budget-bound recursion. D009's REQUIRED Budget
invariant is not theoretical caution; it is the field norm.

### 3.2 Schema validation = our verification layer

`output_schema` (pydantic model / generic / primitive / raw JSON Schema) is
validated on **every** `FINAL(...)`; on failure the agent receives the schema +
the specific validation errors and may retry within its call budget. This is the
RLM analogue of our `VerifiedToolResult` + `EvidenceLedger` anti-fancy layer
(M014). It confirms D011 §10.4: verification is not waived by RLM.

Sub-agents inherit a schema via `llm_query(prompt, schema)` — the child enforces
the same shape. This maps to typed contracts between RGLA sub-Loops.

### 3.3 REQUIRED `primary_agent` = injected-provider discipline

There is **no default model**: every `run()` requires
`RLMConfig(primary_agent="...")`. This matches our R002 / M038 discipline —
providers are injected (`LLMRouter`), there is no ambient default. fast-rlm
makes the absence-of-default a hard error, which is the stance our
`test_init_rejects_missing_*` tests encode.

### 3.4 Backend-agnostic port (incl. ACP)

Four backends via the `primary_agent` string:
- OpenAI-compatible (OpenRouter default / DeepSeek / MiniMax / any)
- Vertex AI (ADC auth)
- Native Anthropic
- **ACP coding agents** (`acp:codex`, `acp:claude-code`, `acp:opencode`) —
  read-only, no API key needed

This maps onto our `LLMProviderPort`. The **ACP mode** — driving a local coding
agent read-only — is a notable future adapter candidate: it would let an RGLA
Loop delegate a sub-task to a real coding agent without network/LLM spend.

### 3.5 Tools as REPL callables

User tools are ordinary Python functions passed to `run(..., tools=[fn])`; they
are pre-loaded into the root REPL namespace; the model sees name + arg names +
docstring (not internal code). This aligns with our `ToolRegistry` +
`ToolCapability` + `ToolResult` — tools are functions behind a port, not a
separate calling protocol.

### 3.6 Structured input informs the Context Graph port (§9 Q3)

When `query` is a `dict`, fast-rlm prints a **flat top-level schema probe** at
step 0 (keys + type + length + truncated preview) so the model can index
`context["reviews"]` directly instead of stringifying. This is direct evidence
for `doc/rgla.md` §9 Q3: an externalised-context port should present structure,
not a flattened string. It sharpens the Context Graph contract.

## 4. Engineering caveats (honest)

- **Heavy native dependency.** Deno 2+ (and Pyodide) is a non-trivial runtime.
  If ever adopted, it lives strictly behind an L3 adapter; never in
  domain/application (R002).
- **Code-execution trust boundary.** The sandbox runs model-written code. Our
  `VerifiedToolResult`/`EvidenceLedger` must still gate outputs; RLM does not
  waive verification (D011 §10.4).
- **Single-author, fast-moving.** Treated as a pattern reference, not a vendored
  runtime. No commitment to track its releases.
- **No graph.** fast-rlm is REPL/filesystem-centric (the "Unix RLM" flavour), not
  graph-backed. It does not address LoopGraph provenance — that remains our
  differentiator (D009/D010). fast-rlm is the *reasoning* mechanism; LadybugDB
  remains the *provenance* store.

## 5. Case study: structured outputs as the sub-agent boundary (free-text swarm failure)

A concrete failure-mode analysis (neural_avb, on the same fast-rlm engine)
clarifies *why* typed contracts at sub-agent boundaries matter — and it lands
 squarely on patterns this project already has.

### 5.1 The failure mode: free-text fan-out

Task: answer a question about an implicit, distributed fact in a 107k-char
 novel (LongBench/NarrativeQA). The model chose the classic RLM fan-out:
 chunk the context, spawn ~62 depth-1 sub-agents, each with a **free-text**
 instruction ("describe Saltram's living situation"), then aggregate.

Result: ~62 near-identical prose responses ("the passage does NOT contain…").
The aggregator is flooded with confounding text, loses the thread, and
 hand-writes a wrong answer — especially for weaker reasoning models. The RLM
 prompt shape *encourages* this fan-out, but without structure it breaks on
 distributed/implicit truths that require **joining** information, not keyword
 search.

### 5.2 The fix: structured-output routing

Same fan-out, but sub-agents return a **typed** value (here a simple boolean:
 "does this chunk contain relevant info?") enforced by fast-rlm's `output_schema`
on every `FINAL(...)`. The aggregator now sees clean boolean flags, not 62 prose
 variations, and reads only the relevant chunks of the original context.

This behaves as **external sparsification / an attention mask**: the model
 never loads large irrelevant regions into context at once. Hallucination risk
 drops because there is less noise and the model does not "lose the plot".

### 5.3 The load-bearing insight for RGLA

> **Typed outputs at sub-Loop boundaries are an evidence-routing layer — and
> that layer is more durable than any specific RLM engine.**

Two consequences that reshape RGLA's contracts:

1. **Sub-Loop contracts must be typed, not free-text.** A RGLA Loop spawning
   sub-Loops should declare each child's output schema (JSON Schema / pydantic /
   domain dataclass). This is the RLM analogue of our `VerifiedToolResult` and
   the natural form of a LoopGraph provenance edge: the edge carries a typed,
   validated payload, not a prose blob.

2. **Typed outputs are the durable layer; the RLM engine is replaceable.**
   Models change, RLM harnesses change, but typed evidence + provenance +
   confidence survive. This is exactly the bet RGLA makes: LoopGraph provenance
   (typed edges) is the long-lived asset; fast-rlm / ACP / any RLM engine is a
   swappable L3 adapter behind the port.

### 5.4 Reinforced discipline (no relaxation)

The case study confirms rather than weakens D011 §10.4:
- Verification is **not optional** — it is the difference between a reliable
  reduce and a confounded one. fast-rlm enforces schema on every `FINAL()`;
  RGLA must enforce a typed contract on every sub-Loop return.
- The `VerifiedToolResult` + `EvidenceLedger` pair (M014) is the right shape;
  the case study shows *why* free-text boundaries fail.
- The new `BudgetExhausted` / `LLMUnavailable` typed errors (M040) are how a
  fan-out that cannot validate degrades, rather than hand-writing a guess.

## 6. Net effect on project decisions

| Decision | Effect |
|----------|--------|
| D009 (REQUIRED Budget) | **Strengthened** — fast-rlm proves budget-bounded recursion is the field norm |
| D011 §10.4 (verification not relaxed) | **Strengthened** — case study (§5) shows free-text boundaries fail; typed contracts are required |
| D011 (Golden Sessions) | Unchanged; fast-rlm has no equivalent (it is stateless per-run) |
| **Sub-Loop contract shape (new)** | **Sharpened** — every RGLA sub-Loop return must be typed; the typed payload IS the LoopGraph provenance edge payload |
| **Durable-layer bet (new)** | **Affirmed** — typed evidence + provenance outlive any RLM engine; engines are swappable L3 adapters |
| §9 Q3 (Context Graph port) | **Sharpened** — externalised context should be structured, not stringified |
| Future adapter candidates | **Added** — ACP mode (`acp:codex` etc.) is a candidate read-only delegation adapter |
| Adoption as dependency | **Out of scope** — studied for patterns only |

## 7. Open follow-ups (not started)

1. Run the project's current harness/evolution workflow through the RLM 7-gate
   rubric (D011 §10.3) to prioritise the next milestone. (Requires fetching the
   exact 7-gate definitions from `rawwerks/recursive-coding-agents`.)
2. Prototype an ACP-mode `LLMProviderPort` adapter that delegates a sub-task to a
   local coding agent read-only — the most directly transferable fast-rlm idea.
3. Decide whether the Context Graph port (§9 Q3) should adopt fast-rlm's
   "flat schema probe at step 0" pattern for its structural presentation.
4. **Define the typed sub-Loop contract** (schema-bearing return) as the
   canonical LoopGraph provenance edge payload — the most directly actionable
   RGLA contract from this research (§5.3).
