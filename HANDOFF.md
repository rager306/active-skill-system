# Handoff — GSD workflow MCP readiness fix

## Last action

Patched the installed runtime copy of GSD, not the vendor clone, to fix Claude Code `discuss-milestone` preflight false negatives when workflow MCP tools are supplied via inline SDK `mcpServers`.

Changed files:

- `/root/.gsd/agent/extensions/mcp-client/manager.js`
- `/root/.gsd/agent/extensions/gsd/tool-surface-readiness.js`
- `/root/.gsd/agent/extensions/claude-code-cli/stream-adapter.js`

Verification run before handoff:

```text
imports: ok
inline config passed to probe: ok
last error surfaced: ok
real inline probe: {"ok":true,"missing":[]}
awaitWorkflowMcpToolRegistration real inline: ok
```

## Current state

- GitNexus MCP is connected via `/root/.gsd/mcp.json` as `gitnexus` using `npx --yes gitnexus mcp`.
- Fresh `open-gsd/gsd-pi` clone exists at `/root/vendor-source/gsd-pi`.
- That clone is indexed by GitNexus and up to date at commit `1b459c4`.
- Worktree isolation is disabled in `.gsd/PREFERENCES.md`:

```yaml
git:
  isolation: none
```

## Root cause summary

`stream-adapter.js` built inline phase MCP config for Claude SDK (`sdkOpts.mcpServers`) but `awaitWorkflowMcpToolRegistration` only probed by server name through persisted MCP config lookup. If persisted config was missing, stale, or different, preflight could fail with:

```text
workflow tool surface not ready for discuss-milestone: MCP server "gsd-workflow" did not register required tools before session start: ask_user_questions, gsd_summary_save, gsd_requirement_save, gsd_requirement_update, gsd_plan_milestone, gsd_milestone_generate_id
```

The MCP server itself does register the tools; the bug was split-brain readiness validation plus hidden probe errors.

## What changed

1. `manager.js`
   - Added `normalizeMcpServerConfigForProbe(name, config)` export.
   - It converts inline SDK MCP config into the existing managed config shape for `testMcpServerConnection`.

2. `tool-surface-readiness.js`
   - Imports `normalizeMcpServerConfigForProbe`.
   - `awaitWorkflowMcpToolRegistration` now accepts `input.workflowServerConfig`.
   - Default probe uses the inline config when provided, falling back to name lookup otherwise.
   - Tracks `lastError` and appends `Last probe error: ...` to timeout diagnostics.

3. `stream-adapter.js`
   - Computes:

```js
const workflowMcpServerConfig = workflowMcpServerName && isRecord(sdkOpts.mcpServers)
    ? sdkOpts.mcpServers[workflowMcpServerName]
    : undefined;
```

   - Passes `workflowServerConfig` into `awaitWorkflowMcpToolRegistration`.

## Next action after restart

1. Restart/reload GSD/pi so the modified installed ESM modules are reloaded.
2. Re-run the previously failing `discuss-milestone` flow.
3. If it still fails, inspect whether the new error includes `Last probe error:`; that should now reveal the real cause.
4. If runtime fix works, port the same patch to `/root/vendor-source/gsd-pi/src/...` TypeScript sources, add tests, and create a PR for issue #808.

## Related GitHub artifacts

- Issue: https://github.com/open-gsd/gsd-pi/issues/808
- Comment linking related PR #731: https://github.com/open-gsd/gsd-pi/issues/808#issuecomment-4768019759
- Related partial PR: https://github.com/open-gsd/gsd-pi/pull/731

## Do not

- Do not edit only `/root/vendor-source/gsd-pi` if the goal is to fix the currently installed runtime; live GSD uses `/root/.gsd/agent/extensions/...` in this session.
- Do not assume a persisted `.mcp.json` exists or matches Claude SDK inline `mcpServers`; that mismatch was the bug.
- Do not drop the `Last probe error` diagnostic when porting to TypeScript; it is part of the fix.
