---
name: fastcontext
description: Explore unfamiliar codebases with the local FastContext MCP tool to locate implementations, trace dependencies, and gather source citations. Use for broad repository discovery; use direct reads or search for known files and exact symbols.
---

# FastContext

Use `fastcontext_explore` to gather candidate source locations with a local 4B MLX model on Apple Silicon. The engine verifies returned paths and line ranges against observed, unchanged source content and omits model-written explanations. Treat the citations as leads: relevance and completeness still require direct source verification.

## Choose the tool and repository

- Use FastContext for unfamiliar implementations, relationships across files, or architecture discovery.
- Use direct reads for known files and direct search for exact symbols or simple keyword lookups.
- Pass `work_dir` as the **absolute path of the intended repository or worktree** on every call. A shell `cd` does not change an already running MCP server's directory.
- If `work_dir` is omitted, the server uses its launch directory for compatibility. Do not assume that directory matches the current project.
- If the tool is unavailable, check tool discovery, registration, and connection before concluding it is uninstalled. Use the `fastcontext-setup` skill when available, or report the missing connection and continue with direct search. Do not install software solely because a tool is absent from the current tool list.

## Call the tool

```text
fastcontext_explore(
  query="Find TypeScript authentication middleware and JWT validation; trace where routes register it",
  work_dir="/absolute/path/to/repository",
  max_turns=4
)
```

| Parameter | Default | Guidance |
|---|---|---|
| `query` | Required | State the behavior or relationship to locate; include known names, paths, language, or error text when useful. Do not invent anchors. |
| `work_dir` | Server launch directory | Absolute repository/worktree directory; always supply it for predictable scope. |
| `max_turns` | 4 | Clamped to 1–10; try 2 for narrow discovery, 4 normally, or 6–8 when evidence warrants deeper exploration. |

Prefer one coherent question per request. Split unrelated questions when it improves focus, but do not assume multiple calls are faster: each request reloads the model and shares one inference slot with other clients.

Examples:

- “Find Python CLI entry points and trace how subcommands are registered.”
- “Locate the React settings form and the API handler that persists its values.”
- “Trace where `ConnectionRefusedError` is handled in the worker retry path.”

## Verify and recover

Read the cited source and check that it supports the conclusion before reporting it as fact or editing it. Resolve relative citations against `work_dir`; check absolute citations belong to the intended project. Missing files, implausible paths, or unsupported claims are reasons to inspect scope and use direct search.

If a focused query fails, refine it with facts already observed or fall back to direct reads/search. Avoid repeated speculative retries. An explicitly partial result contains only the citations that passed verification; it does not establish full coverage of the question. An empty or incomplete result does not prove an implementation is absent. Respect the caller's authorization and repository instructions when following citations.

## Resource lifecycle

Each client keeps a lightweight MCP connection. An exploration starts a disposable MLX worker using `rubybear/FastContext-1.0-4B-SFT-mlx-4bit-g32`. A machine-wide lock allows only one worker to load a model at a time; concurrent requests wait.

The worker resolves ripgrep (`rg`) from its `PATH`; search requires that binary to be installed and visible to the MCP process.

The worker exits after its request, releasing model and KV-cache memory. KV cache reuse applies within one exploration, not between requests. Cancellation, parent disconnect, or the 10-minute worker deadline triggers cleanup. The deadline includes waiting for the machine-wide inference slot; requests queued within one client wait before their worker starts. On-disk model files remain cached. Expect a loading delay on each request.
