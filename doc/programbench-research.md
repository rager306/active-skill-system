# ProgramBench — external benchmark track research

> Status: **research / benchmark evaluation**. ProgramBench is adopted as a
> second benchmark track for the maxi-goal (D013): a heavy, honest, external
> measure of framework progress on holistic software engineering. NOT a
> replacement for the mini feature-slice benchmark. Companion to D014.
>
> Source: arXiv:2605.03546 (Meta FAIR/SIL, 2026-05); programbench.com;
> github.com/facebookresearch/ProgramBench; HuggingFace programbench/ProgramBench-Tests.

## 1. What ProgramBench is

A benchmark for **holistic software engineering**: can an LLM/agent rebuild a
complete program from scratch given only a compiled binary + documentation, with
no internet, no decompilation, no source (clean-room). The agent must design the
architecture, choose a language, write multi-file code, set up the build, and
achieve full behavioural parity with the original.

- **200 tasks** from real GitHub repos: small CLI utilities → FFmpeg, SQLite,
  PHP interpreter, tinycc, ripgrep, DuckDB, zstd.
- Median task: ~8635 LOC, ~50 files, ~10 runtime deps.
- **Evaluation:** auto-generated behavioural tests (pytest-style,
  coverage-guided, ~80% line coverage, thousands of tests per task).
- **Metrics:** Resolved (100% tests pass), Almost Resolved (≥95%).

## 2. Why it fits the maxi-goal (D013)

D013's maxi is a comprehensive SDLC harness with emphasis on **heavy
high-level architectural prototyping**. ProgramBench hits exactly that: the
agent must make architecture decisions, organise a codebase, handle edge cases —
not just patch a bug (SWE-bench) or write one function (HumanEval). It gives the
project a ready-made external standard instead of inventing its own benchmark.

## 3. Honest assessment (fitness + risks)

| Dimension | Assessment |
|-----------|------------|
| Fitness for maxi | Strong — holistic SE, architecture, multi-file |
| Difficulty | Extreme — frontier models 0–0.5% Resolved (May–Jun 2026 leaderboard) |
| Realistic expectation for this framework | **0% Resolved** on most tasks; progress visible in Almost Resolved + strategy evolution + failure-mode LoopGraph |
| Cost | High — 200 tasks × many iterations × many models = large LLM spend + wall time |
| Scope match | One facet of SDLC (reconstruct-from-behaviour), NOT all of maxi (from-scratch architectural prototyping is a different class) |
| Toolchain need | Sandbox must compile/run code (gcc/clang/cargo) — available in env |
| Dataset availability | Ready (HuggingFace ProgramBench-Tests, GitHub repo) — no construction cost |

**Key honesty:** ProgramBench measures reconstruct-from-behaviour. It is a
*second track*, not a replacement for the mini feature-slice (which measures how
an agent arrives at a known answer). The mini stays the fast evolution loop;
ProgramBench is the slow, honest, external validator.

## 4. How the two tracks compose (D013 + D014)

```
MINI track (D013, fast evolution loop):
  feature-slice benchmark — project knows the answer
  → measures HOW agent+model arrives
  × many iterations × many models
  → LoopGraph provenance + ratchet per run
  → fitness comparable across models/iterations

PROGRAMBENCH track (D014, slow external validator):
  1-2 smallest CLI tasks (NOT median/FFmpeg/SQLite)
  → measures PROGRESS of the framework vs frontier (0.5%)
  → Almost Resolved + LoopGraph failure-modes ("where the agent breaks")
  → informs which evolution-step the maxi needs next
```

The mini feeds evolution quickly; ProgramBench validates that the evolved
strategies generalise to an external, honest, hard standard.

## 5. Starting point (when the build milestone arrives)

Start with **1-2 smallest CLI tasks** from the 200. Reasoning:
- frontier is 0.5% Resolved → expecting Resolved is self-deception.
- smallest CLI gives the best chance of measurable movement (Almost Resolved)
  within a bounded budget.
- the signal is **LoopGraph failure-modes**: where does the agent break
  (architecture choice? edge cases? dependency wiring? build setup?). That
  diagnosis drives the next evolution step — which is the actual maxi growth.

## 6. What stays deferred

- Median/large tasks (FFmpeg/SQLite/etc.): deferred until smallest CLI shows
  measurable Almost-Resolved movement.
- Running all 200 tasks: deferred — cost/benefit unfavourable until the
  framework's per-task strategy improves.
- Treating ProgramBench as the *only* benchmark: declined — it is one facet;
  the mini feature-slice remains the fast loop.

## 7. Verification still needed (before first run)

Before the build milestone executes a ProgramBench run, verify in-env:
- the ProgramBench harness installs (github.com/facebookresearch/ProgramBench).
- a smallest task's binary + behavioural tests are loadable from the HF dataset.
- the sandbox can compile/run the chosen task's language.

These are build-milestone prerequisites, not blockers for recording D014.
