# Sandbox isolation — research note

> Status: **research / security gap assessment**. A real vulnerability in the
> current sandbox is identified: LLM-generated code is executed via importlib
> with full process privileges. Companion to D018.
>
> Source: 2026 sandbox-isolation research (nsjail/bubblewrap/seccomp/Landlock/
> cgroups/Firecracker); environment verification 2026-06.

## 1. The vulnerability

`application/use_cases/sandbox_verifier.py` loads candidate modules via
`importlib.util.spec_from_file_location` + `exec_module`. This is NOT isolation
— the LLM-generated code runs with full process privileges. If a model generates
malicious code (`os.system`, network, file access), it executes unprotected.
The code comment claims "isolated namespace" — that is a module namespace, not
process isolation. This is a **security gap** that must close before the maxi
(D013 SDLC harness / ProgramBench) where agents generate complex multi-file code.

## 2. Available isolation backends in this environment (verified)

| Backend | Available? | Isolation level | Notes |
|---------|-----------|-----------------|-------|
| **bubblewrap (bwrap)** | ✅ v0.9.0 installed | Namespaces (mount/pid/net/user) + `--unshare-all` | CLI, very low overhead; production-tested (Flatpak) |
| **Landlock** | ✅ kernel LSM active | Filesystem access control (no-root) | Python `landlock` lib not installed but kernel supports it |
| **seccomp (libseccomp2)** | ✅ installed | Syscall whitelist/blacklist | Hardest part: Python needs many syscalls; build profile incrementally |
| **nsjail** | ❌ not installed | Comprehensive (namespaces + seccomp + cgroups built-in) | Google; Windmill uses it for Python; more setup |
| **Pyodide (WebAssembly)** | ❌ not installed | WASM sandbox (like fast-rlm's Deno+Pyodide) | Separate runtime; safest process-level isolation |
| **Firecracker microVM** | ❌ not installed | VM-level (kernel isolated) | Heaviest; maxi production candidate |

## 3. Architecture: CodeExecutorPort (same pattern as ReasoningEnginePort)

```
application/ports/code_executor.py   ← CodeExecutorPort Protocol
adapters/inprocess_executor.py       ← importlib (current, for deterministic tests)
adapters/bwrap_executor.py           ← bubblewrap + unshare-all (production)
adapters/nsjail_executor.py          ← (future) strictest production
adapters/pyodide_executor.py         ← (future) WebAssembly, like fast-rlm
```

Strategy selection = composition-time. InProcess for offline tests (fast,
deterministic); BwrapExecutor for real-LLM runs (isolated). The verifier and
sandbox runner delegate through the port, not importlib directly.

## 4. Recommended first build (when prioritised)

**BwrapExecutor** — bubblewrap is already installed and is the lightest real
isolation:

```bash
bwrap --ro-bind /usr /usr --ro-bind /lib /lib --ro-bind /lib64 /lib64 \
  --bind /tmp/sandbox_XXXX /tmp --dev /dev --proc /proc \
  --unshare-all --die-with-parent --new-session \
  python3 -c "import sys; exec(open(sys.argv[1]).read())" candidate.py
```

Then layer seccomp + Landlock as the need grows. nsjail if a more
comprehensive policy is needed. Pyodide as a separate strategy (WebAssembly
sandbox, matching fast-rlm's approach).

## 5. Honest assessment

- **Current importlib is acceptable ONLY for deterministic offline tests** where
  the candidate source is known (fixtures, FakeReasoningEngine). For real-LLM
  generated code, it is a vulnerability.
- **bubblewrap is the right first step** — installed, CLI, production-tested,
  very low overhead. Not absolute isolation (process-level, kernel accessible),
  but a massive improvement over importlib.
- **seccomp for Python is the hard part** — Python makes many syscalls; build
  the whitelist incrementally (run with logging → generate rules).
- **For maxi production**, Firecracker or nsjail may be needed. bubblewrap is
  the development-time floor.
