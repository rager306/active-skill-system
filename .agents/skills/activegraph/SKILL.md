---
name: activegraph
description: >-
  ActiveGraph event-sourced reactive graph runtime integration and findings:
  setup (uv / Python 3.13), the event-log / projection / fork / diff / replay /
  behavior / pack model, MiniMax-via-Anthropic-compatible-gateway LLM wiring,
  and known integration gaps. Use when building on, running, debugging,
  integrating LLM providers with, or reasoning about activegraph
  (github.com/yoheinakajima/activegraph), its runs/event log/fork/replay, the
  Diligence pack, or routing MiniMax (MiniMax-M3) through its Anthropic-compatible endpoint.
---

<objective>
Work with ActiveGraph (github.com/yoheinakajima/activegraph) effectively: set it
up, run/inspect/fork/diff/replay runs, wire real LLM providers (especially
MiniMax-M3 via the Anthropic-compatible gateway), and avoid repeating known
integration mistakes. This is the living log of project findings — read
`references/activegraph-findings.md` before implementing or debugging
activegraph code, and append new findings there as they are discovered.
</objective>

<quick_start>
Read `references/activegraph-findings.md` before implementing or reviewing
activegraph code.

Setup (verified, Python 3.13.12 + uv, activegraph 1.1.0 from the clone):

```bash
uv venv --python 3.13 /tmp/ag-box
uv pip install --python /tmp/ag-box/bin/python /root/vendor-source/activegraph
# optional LLM extras: '/root/vendor-source/activegraph[llm]'
# + python-dotenv for .env-driven config
```

Key facts (all verified against commit `27c2901b`, see findings):

- **Python 3.13 works** (`requires-python >=3.11`, no upper bound; classifiers
  list only 3.11/3.12 but 3.13 is empirically fine). Hard deps: `click>=8,<9`,
  `pydantic>=2`.
- **The graph is the world, the event log is the proof.** `EventStore` is an
  append-only per-run log; the graph is a projection rebuilt from the log
  (`replay` rebuilds it without firing behaviors). `Runtime.fork` copies the
  parent prefix and diverges after a branch point; `diff` compares two runs
  (shared = byte-identical payloads, not just prefix length).
- **Behaviors are thin reactive adapters.** `@behavior(on=[...], creates=[...])`,
  signature `(event, graph, ctx) -> None` (CONTRACT #6). No business logic, no
  direct I/O (breaks replay/fork reproducibility).
- **Determinism is record-replay, not formal.** `quickstart` is byte-deterministic
  (FrozenClock + fixed run id + seeded + cached LLM). A fork needing new LLM
  calls is non-deterministic by definition.
- **MiniMax via the Anthropic-compatible gateway:** `ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic`,
  auth as `ANTHROPIC_AUTH_TOKEN` (Bearer; the SDK reads it), model
  `MiniMax-M3` / `MiniMax-M3-512k` (legacy alias; the gateway normalizes to
  M3 with a 1,000,000-token context window). Load from the project `.env` via
  `python-dotenv`. `AnthropicProvider` hard-requires `ANTHROPIC_API_KEY` — use a
  thin `MiniMaxProvider(AnthropicProvider)` that bypasses that check (see
  findings). activegraph's model validation accepts `MiniMax-M3` (permissive).
- **MiniMax-M3 specific (api-reference-verified):** `thinking` is OFF by
  default and must be enabled with `thinking={"type": "adaptive"}` in every
  `messages.create` call (the `MiniMaxProvider` does this when
  `enable_thinking=True`, the default for M3 models). `count_tokens` (POST
  `/anthropic/v1/messages/count_tokens`) IS supported for M3 — use real +
  fallback on tool-loop message shapes. `temperature` range is [0, 2] (rec.
  1.0); `top_p` default 0.95 for M3. Ignored by gateway (safe to send but
  ineffective): `top_k`, `stop_sequences`, `mcp_servers`, `context_management`,
  `container`. See findings §5.1 and the official api-reference at
  `https://platform.minimax.io/docs/api-reference/text-anthropic-api`.
- **Diligence pack goal must start with `Diligence:`** (the `company_planner`
  guard) or the reasoning cascade never fires.

CLI (black-box controls): `quickstart`, `inspect <url>`, `fork <url>
--run-id --at-event`, `diff <url> --run-a --run-b`, `replay <url> --run-id`,
`export-trace <url>`, `migrate`, `pack`. Store URL form: `sqlite:////abs/path.db`.
</quick_start>

<essential_principles>
<principle name="event_log_is_source_of_truth">
The append-only event log is the execution history; the object graph is a
materialized projection rebuilt from it (`replay_into` / `Graph._replay_event`,
used by `Runtime.load` and `Runtime.fork`). Treat the log as durable truth, the
graph as a derived view.
</principle>

<principle name="behaviors_are_thin_adapters">
Behaviors subscribe to events (`on=`) and may create objects/relations
(`creates=`); they must be deterministic and side-effect-free (no direct I/O)
or replay/fork stop being reproducible. Business logic belongs in the
domain/application layer, not in behavior bodies.
</principle>

<principle name="determinism_is_record_replay">
"Reproducible" means replay-the-same-cached-trajectory, not formal determinism.
LLM outputs are cached in the event log (`LLMCache.from_events`,
`ToolCache.from_events`) and served on replay; `ReplayDivergenceError` aborts on
prompt/version divergence. Forks needing new LLM calls are non-deterministic.
</principle>

<principle name="fork_prefix_then_diverge">
Fork copies events up to and including a branch-point event into a new run, then
diverges. `diff` shared_events counts byte-identical payloads (including
run_id context), which is stricter than prefix length — model run-scoped data
accordingly.
</principle>

<principle name="model_validation_is_permissive">
`_validate_one` rejects a model name only if it is claimed by a *different
shipped* provider (e.g. gpt-* on an Anthropic runtime). A name no shipped
provider claims (e.g. `MiniMax-M3`) passes silently. So custom/third-party model
names work without patching validation.
</principle>

<principle name="minimax_auth_token_not_api_key">
For the MiniMax Anthropic-compatible gateway, the working claude-code setup uses
`ANTHROPIC_AUTH_TOKEN` (Bearer), not `ANTHROPIC_API_KEY`. The `AnthropicProvider`
hard-requires `ANTHROPIC_API_KEY` and raises otherwise — bypass with a thin
subclass whose `_client()` returns `Anthropic()` (the SDK then uses
`ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL`).
</principle>

<principle name="config_in_env_not_code">
LLM endpoint/auth/model belong in the project `.env` (gitignored), loaded via
`python-dotenv` (`override=True`). Never hardcode secrets; never ask the user to
edit env by hand.
</principle>
</essential_principles>

<known_gaps>
<gap name="minimax_tool_loop_error_2013" status="RESOLVED 2026-06-23">
Multi-turn tool-driven behaviors failed with MiniMax error `2013 "tool result's
tool id() not found"`. Root cause: `Runtime` rebuilt the assistant turn in the
tool loop from `raw_text + tool_calls` and **dropped `thinking` blocks**
(`runtime/runtime.py` ~1171); MiniMax M3 (interleaved thinking) rejected the
result. RESOLVED in the L3 adapter (`MiniMaxProvider`): cache each response's
full raw.content blocks (thinking+text+tool_use) by tool_use_id and restore
them on the next turn (per the official M3 "preserving-thinking-blocks" guide).
Two companion fixes landed alongside: `count_tokens` now tries the real gateway
endpoint (M3 supports it) with a chars/4 fallback for tool-loop shapes; and
`thinking={"type": "adaptive"}` is sent by default for M3 so the shim above
actually has blocks to preserve. End-to-end Diligence→memo on MiniMax-M3 now
passes (0 failures, claims + memo). See findings §5.1.
</gap>
</known_gaps>

<anti_patterns>
Do not:
- assume "deterministic/reproducible" means formal determinism (it is
  record-replay);
- put business logic, HTTP, or non-deterministic I/O inside a behavior body;
- use `ANTHROPIC_API_KEY` with the MiniMax gateway and expect the default
  `AnthropicProvider` to work (it raises) — use the `ANTHROPIC_AUTH_TOKEN` path;
- drop `thinking`/`reasoning`/`tool_use` blocks from multi-turn tool history
  (breaks MiniMax M3 tool loops);
- run the Diligence pack with a goal that does not start with `Diligence:`
  (the `company_planner` guard silently no-ops and the cascade never fires);
- treat a fork's `shared_events` as equal to its copied-prefix length (shared
  requires byte-identical payload);
- for MiniMax-M3: omit `thinking={"type": "adaptive"}` from `messages.create`
  kwargs (thinking is OFF by default — the model will not reason, and a
  thinking-preservation shim caches nothing);
- rely on `temperature > 1.0` or `temperature == 0` for M3 (range is [0, 2],
  recommended 1.0; 0 is invalid);
- rely on `top_k`, `stop_sequences`, `mcp_servers`, `context_management`, or
  `container` for M3 — the gateway silently ignores them;
- treat the global skill `minimax-safe-helper` (`/root/.agents/skills/`) as
  authoritative for the Anthropic-compatible surface: as of 2026-06-23 its
  "(0.0, 1.0]" temperature range and X-Api-Key guidance conflict with the
  official api-reference and with what claude-code/Bearer actually does. Use
  api-reference + this skill instead.
</anti_patterns>

<validation>
Before claiming activegraph work is complete, verify:
- runs against the intended provider/endpoint (inspect the run: `events_processed`,
  `llm.responded` with model + cost);
- behaviors are deterministic (replay reproduces; no direct I/O);
- fork/diff behave as prefix-copy + tail-divergence;
- for MiniMax: `ANTHROPIC_AUTH_TOKEN` (not `ANTHROPIC_API_KEY`) is used and
  tool-driven behaviors apply the thinking-preservation shim with
  `thinking={"type": "adaptive"}` enabled for M3;
- for MiniMax-M3: `temperature` is in [0, 2] (recommended 1.0); `top_p` is in
  [0, 1] (default 0.95); `count_tokens` either uses the gateway endpoint or
  the offline fallback heuristic when tool-loop shapes may be rejected;
- secrets stay in `.env` (gitignored), never in code or logs;
- QA stack is green: ruff, ty, pyrefly, import-linter, pytest (+xdist),
  hypothesis, and **pytest-gremlins** (mutmut has been retired). Smoke-run
  `pytest --gremlins` on changed modules; require 0 survivors.
</validation>

<success_criteria>
ActiveGraph work follows this skill when:
- setup uses uv + Python 3.13 with the clone (or PyPI) and the right extras;
- the event-log/projection/fork/diff/replay model is respected in design and
  debugging;
- LLM wiring (especially MiniMax) uses `.env` + dotenv + the `ANTHROPIC_AUTH_TOKEN`
  path + a `MiniMaxProvider` shim where needed;
- known gaps (MiniMax tool-loop 2013) are recognized and either avoided or
  shimmed;
- new findings are appended to `references/activegraph-findings.md`.
</success_criteria>

<reference_index>
- `references/activegraph-findings.md` — verified setup, CLI black-box checks,
  architecture/source locations (event log, projection, fork/diff, behaviors,
  packs, model validation), MiniMax integration recipe + the tool-loop gap, and
  the Diligence pack as a reasoning-Task-Graph precedent. Append new findings here.
</reference_index>
