# activegraph-findings

Living log of verified findings about ActiveGraph
(`github.com/yoheinakajima/activegraph`). Append new findings as they are
discovered; keep entries dated and evidence-backed (commit / file:line / command
output). Canonical index for the `activegraph` skill.

Last verified commit: `27c2901b` (2026-06-10), re-cloned + re-indexed via
GitNexus (4936 nodes / 9544 edges / 251 files / 300 flows).

## 1. Setup (verified 2026-06-23)

```bash
uv venv --python 3.13 /tmp/ag-box                       # Python 3.13.12
uv pip install --python /tmp/ag-box/bin/python /root/vendor-source/activegraph
uv pip install --python /tmp/ag-box/bin/python '/root/vendor-source/activegraph[llm]' python-dotenv
```

- `requires-python = ">=3.11"` (no upper bound) — 3.13 is allowed; classifiers
  list 3.11/3.12 only, but 3.13 works empirically (deps `click 8.4.1`,
  `pydantic 2.13.4`, `anthropic 0.111.0` all resolve clean).
- Hard deps: `click>=8,<9`, `pydantic>=2`. Extras: `[llm]` (anthropic+openai+
  tiktoken), `[anthropic]`, `[openai]`, `[postgres]`, `[prometheus]`,
  `[opentelemetry]`, `[all]`. SQLite store is stdlib (no extra).
- Entry point: `activegraph = activegraph.cli.main:main`. Diligence pack
  registered under `activegraph.packs` entry point group.

## 2. Black-box verification (CLI)

```bash
activegraph quickstart                                  # recorded fixtures, no API key, byte-deterministic
activegraph inspect   sqlite:////abs/path.db            # run status (state, events_processed, budget, tail)
activegraph fork      sqlite:////abs/path.db --run-id <run> --at-event evt_NNN --label <l>
activegraph diff      sqlite:////abs/path.db --run-a <a> --run-b <b>
activegraph replay    sqlite:////abs/path.db --run-id <run>
activegraph export-trace sqlite:////abs/path.db         # event log as text/jsonl
```

Verified behaviors (commit 27c2901b):
- `quickstart` is byte-deterministic across runs (FrozenClock + fixed run id +
  seeded + RecordedDiligenceProvider); two runs diff identical.
- `inspect` shows full status; `--event <id>` prints one event payload (use to
  debug `ReplayDivergenceError`, which names the offending event id); selectors
  `--behaviors`, `--pack-version`, `--json`.
- `replay` rebuilds the graph from the log with NO behaviors firing
  (`671 events -> 93 objects / 76 relations`).
- `fork @evt_650` -> new run with 650 events (prefix copy); `diff` shows
  `parent_only` tail objects (e.g. `memo#93 only in parent`), `fork_only=0`;
  `shared_events` counts byte-identical payloads (strict, includes run_id
  context) — stricter than prefix length.

## 3. Architecture / source locations (GitNexus-grounded)

README self-description: "An event-sourced reactive graph runtime for
long-running, auditable, agentic systems. ... Every run is resumable, forkable,
and diff-able from its event log. Cache replay means the shared prefix doesn't
re-execute (no new LLM calls)." Tagline: "The graph is the world. Behaviors are
physics. The trace is the proof."

| Capability | Location (27c2901b) |
|---|---|
| Pack (object/relation types, behaviors, tools, policies, prompts, settings_schema) | `activegraph/packs/__init__.py:530-621` `class Pack`; loader `packs/loader.py` idempotent on name+version |
| Behaviors (thin inbound adapters) | `activegraph/behaviors/decorators.py` `@behavior/@llm_behavior/@relation_behavior`, signature `(event, graph, ctx) -> None` (CONTRACT #6) |
| Append-only event log | `activegraph/store/base.py` `EventStore` (append/iter_events/get_event/count/truncate_after) |
| Graph projection from log | `replay_into` / `Graph._replay_event` (used by `Runtime.load` + `Runtime.fork`) |
| Replay determinism | `LLMCache.from_events`, `ToolCache.from_events`, `ReplayDivergenceError` (`runtime/errors.py:35`), `IDGen.reseed_from_events` |
| Fork/diff | `Runtime.fork` (`runtime/runtime.py:2338-2472`), `runtime/diff.py:Diff/compute_diff`, `SQLiteEventStore.fork_run` |
| Approval primitive | `PendingApproval` (`activegraph/packs/__init__.py:957-971`) |
| Model validation (permissive) | `runtime/_live.py:_validate_one` + `runtime/runtime.py:_resolve_and_validate_llm_models` |
| LLM providers | `activegraph/llm/anthropic.py:AnthropicProvider` (default_model `claude-sonnet-4-5`, recognizes `claude-*`), `openai.py:OpenAIProvider` (`gpt-4o-mini`) |

Note: line ranges are GitNexus-authoritative (count from decorator/docstring);
the source `class` line is often +1.

## 4. MiniMax integration (Anthropic-compatible gateway)

Goal: run activegraph with MiniMax-M3 through
`https://api.minimax.io/anthropic`, reusing the existing claude-code solution
(`/root/minimax.sh`) ported into the project `.env`.

### 4.1 .env (project, chmod 600, gitignored)

Ported from `/root/minimax.sh`. Keys activegraph/the SDK actually read:
`ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic`,
`ANTHROPIC_AUTH_TOKEN=<MiniMax token, Bearer>`, `ANTHROPIC_MODEL=MiniMax-M3-512k`.
(The `CLAUDE_CODE_*` / `ANTHROPIC_DEFAULT_*_MODEL` vars are claude-code
conventions; activegraph ignores them — the model is set in code/provider.)

### 4.2 Load via python-dotenv

```python
from dotenv import load_dotenv
load_dotenv("/root/active-skill-system/.env", override=True)  # .env authoritative
```

### 4.3 MiniMaxProvider shim

`AnthropicProvider` hard-requires `ANTHROPIC_API_KEY` and raises if missing
(`_client()` checks `os.environ.get(self._api_key_env)`). The MiniMax gateway
auths via `ANTHROPIC_AUTH_TOKEN` (Bearer). Subclass to bypass the check and let
the SDK use the Bearer token:

```python
import os
from dotenv import load_dotenv
load_dotenv("/root/active-skill-system/.env", override=True)
from activegraph.llm.anthropic import AnthropicProvider

MODEL = os.environ.get("ANTHROPIC_MODEL", "MiniMax-M3")

class MiniMaxProvider(AnthropicProvider):
    default_model = MODEL
    def _client(self):
        if self._client_override is not None:
            return self._client_override
        from anthropic import Anthropic
        return Anthropic()  # SDK reads ANTHROPIC_AUTH_TOKEN (Bearer) + ANTHROPIC_BASE_URL
```

### 4.4 Verified

- Single-shot LLM call via dotenv-loaded env: 1.8s, correct reply, cost/tokens
  tracked. ✅
- Full Diligence run (company -> questions -> document_researcher): LLM calls
  work (~2s each), but `document_researcher` fails every question — see gap below.
- `Anthropic()` SDK: with only `ANTHROPIC_AUTH_TOKEN` set, uses Bearer; with
  `ANTHROPIC_API_KEY`, uses `x-api-key`. For MiniMax text API the Bearer
  (`ANTHROPIC_AUTH_TOKEN`) path is the one claude-code uses and that works.

## 5. Known gaps / open work

### 5.1 MiniMax multi-turn tool-loop (RESOLVED 2026-06-23)
Two distinct problems combined to break tool-driven behaviors (e.g.
`document_researcher`). Both fixed in `active_skill_system.adapters.llm.minimax`
(L3 adapter) — no activegraph patch.

**(a) MiniMax error 2013 "tool result's tool id not found"** — root cause:
activegraph rebuilds a tool-loop assistant turn from `raw_text + tool_calls`
and DROPS the `thinking` blocks (`runtime/runtime.py` ~1171 →
`_message_to_anthropic` emits only [text, tool_use]). MiniMax-M3 uses
interleaved thinking and, per the official M3 guide ("preserving-thinking-
blocks": "Append the full response.content list ... must be fully
preserved"), rejects the structurally-incomplete turn.
Fix: `MiniMaxProvider.complete()` caches each response's full raw.content
blocks (thinking+text+tool_use) keyed by tool_use_id (`_remember_turn`) and
on the next turn replaces the rebuilt assistant turn with the cached full
content (`_restore_thinking`). Provider-level; thinking (incl. signature) is
not lost. Verified: standalone 2-turn tool loop succeeds; end-to-end Diligence
produces claims + memo.

**(b) `llm.network_error` (phase=count_tokens)** — root cause: with
`max_cost_usd` set, runtime calls `provider.count_tokens()` as a pre-call cost
gate (runtime.py ~906-920); the inherited `AnthropicProvider.count_tokens`
hits `/v1/messages/count_tokens`, which **IS supported for M3** per the
official api-reference, but can reject tool-loop message shapes (rebuilt
assistant turns + tool_result), surfacing as `llm.network_error` in the broad-
except at runtime.py:915-920. (Weather smoke passed earlier only because it set
no cost budget, skipping the gate.)
Fix: override `count_tokens` to **try the real gateway endpoint first**, then
fall back to a chars/4 heuristic on any failure — gives accurate estimates
for normal messages and a safe fallback for tool-loop shapes.

**(c) `thinking` is OFF by default for M3** — per api-reference ("Thinking is
off by default for MiniMax-M3 and can be enabled with `adaptive`"), the model
does NOT emit thinking blocks unless `thinking={"type": "adaptive"}` is sent.
Without this, the shim above caches nothing and M3 runs as a non-reasoning
model. MiniMaxProvider sets `enable_thinking=True` by default (only for
`MiniMax-M3*` model names) and sends `thinking={"type": "adaptive"}` in
`complete()` kwargs. Empirical confirmation: `block types: ['thinking', 'text']`
on a single call; 2-turn weather loop produces `provider_meta.thinking_preserved: True`.

**Result (verified):** `Diligence: northwind robotics` on MiniMax-M3 → 0
behavior.failed, 39 llm.responded, 11 claims + 11 evidence + 1 memo.
Fixture-company requirement: Diligence `fetch_company_docs` serves recorded
docs for fixture names only (e.g. `northwind robotics`); a non-fixture
company yields 0 claims.

**API-reference constraints captured (MiniMax M3, verified from
`platform.minimax.io/docs/api-reference/text-anthropic-api`):**
- Context window: `MiniMax-M3` = **1,000,000** (the `-512k` model name is a
  legacy alias; the gateway normalizes to M3).
- `temperature` range **[0, 2]**, recommended 1.0 (activegraph defaults to 0.7
  — acceptable but suboptimal for M3).
- `top_p` range [0, 1], **default 0.95** for M3, 0.9 for M2.x.
- `thinking`: fully supported; **off by default for M3**; enabled with
  `{"type": "adaptive"}`; M2.x always on, `disabled` is accepted but ignored.
- `count_tokens` (`POST /anthropic/v1/messages/count_tokens`): supported for
  M3; returns input-token usage without generating output.
- Ignored parameters (silently dropped by gateway): `top_k`, `stop_sequences`,
  `mcp_servers`, `context_management`, `container`. Safe to send but they do
  nothing.
- Fully supported: `model`, `messages` (text/image/video/tool_use/tool_result/
  thinking for M3; text+tool_call only for M2.x), `max_tokens`, `stream`,
  `system`, `temperature`, `tool_choice`, `tools`, `top_p`, `metadata`,
  `thinking`, `service_tier` (`standard`|`priority`, priority = 1.5× price,
  faster admission).
- M3 also accepts `image`/`video` in messages (URL or base64; images up to
  10 MB, videos up to 50 MB; Files API for larger videos up to 512 MB).

**Cross-check:** the global skill `minimax-safe-helper` (at
`/root/.agents/skills/minimax-safe-helper/SKILL.md`) conflicts with the
official api-reference on two points as of 2026-06-23 — it states
"Temperature range is `(0.0, 1.0]`" and recommends `X-Api-Key` (or
`ANTHROPIC_API_KEY`) for the Anthropic SDK path, while in practice
claude-code / this project use Bearer auth via `ANTHROPIC_AUTH_TOKEN` and
api-reference allows `temperature` up to 2. Treat api-reference as
authoritative; treat the global skill as advisory until it is patched.

### 5.2 Diligence goal prefix
The Diligence pack's `company_planner` only acts when the goal starts with
`Diligence:` (else it returns and the cascade never fires). Use
`rt.run_goal(f"Diligence: {company}")`.

## 6. Diligence pack as a reasoning-Task-Graph precedent

The shipped Diligence pack is a working example of mapping a reasoning graph
onto ActiveGraph object types + behaviors (relevant to the project's
architecture R1):
- object types: `company, document, question, claim, evidence, contradiction,
  risk, memo`; relations: `addresses, supports, contradicts, references`.
- behaviors: `company_planner` (on `goal.created`), `question_generator`
  (llm, `object.created` where company), `document_researcher` (llm, tools),
  `evidence_linker` (provenance), `contradiction_detector` (anti-fantasy gate,
  on `relation.created`), `risk_identifier`, `memo_synthesizer`.
So the "reasoning Task Graph <-> activegraph world" mapping is not hypothetical;
Diligence ships it.

## 7. Change log

- 2026-06-23: initial findings — setup, black-box verification, architecture
  locations, MiniMax integration (.env + dotenv + MiniMaxProvider), tool-loop
  gap (2013), Diligence precedent. Re-verified at commit `27c2901b`.
- 2026-06-23: **gap 5.1 RESOLVED** — two fixes in the MiniMax adapter (no
  activegraph patch): (a) thinking-preservation in the tool loop (cache full
  raw.content by tool_use_id, restore on echo) per the official M3
  "preserving-thinking-blocks" guide; (b) `count_tokens` overridden to an
  offline chars/4 heuristic (MiniMax gateway doesn't support
  `/count_tokens`, which surfaced as `llm.network_error` when `max_cost_usd`
  was set). End-to-end Diligence→memo on MiniMax-M3 now works (0 failures,
  11 claims + memo). QA stack: ruff/ty/pyrefly/import-linter/pytest(+xdist)/
  hypothesis/mutmut, all green; layering enforced (onion/hex).
- 2026-06-23: **gap 5.1 REFINED** after fully reading the official MiniMax
  api-reference `text-anthropic-api`: (i) `thinking` is OFF by default for M3
  — `MiniMaxProvider` now sends `thinking={"type": "adaptive"}` by default
  (`enable_thinking=True`, M3 models only), so the shim above actually has
  blocks to preserve; empirical proof on the 2-turn weather loop with
  `provider_meta.thinking_preserved: True`. (ii) `count_tokens` IS supported
  for M3 — heuristic was excessive; now real gateway call with chars/4
  fallback on tool-loop shapes. (iii) `M3` context window = **1,000,000**
  (`-512k` is a legacy alias). (iv) Ignored gateway parameters captured:
  `top_k`, `stop_sequences`, `mcp_servers`, `context_management`, `container`.
  (v) `temperature` range [0, 2] (rec. 1.0); `top_p` default 0.95 for M3.
  Cross-check against global `minimax-safe-helper` flagged 2 conflicts (its
  "temperature (0, 1]" and X-Api-Key guidance are stale; api-reference and
  working claude-code Bearer path take precedence). Mutmut REPLACED with
  **pytest-gremlins 1.8.1** — smoke on `minimax.py`: **40/40 gremlins killed
  (100%)**, 0 survived, HTML+JSON reports in `coverage/gremlins/`.
  Operators configured: `arithmetic|boolean|boundary|comparison` (`return_value`
  not present in this gremlins version).
