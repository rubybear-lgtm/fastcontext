---
name: fastcontext
description: This skill should be used when the user asks to "explore the codebase", "find related files", "understand the architecture", "search for implementations", "use FastContext", or when broad codebase context is needed before editing unfamiliar code. Runs Microsoft FastContext with in-process MLX inference on Apple Silicon.
---

# FastContext

FastContext is a specialized exploration agent that runs Read, Glob, and Grep operations in parallel using a local 4B model via MLX, returning compact file-path:line-range citations. The model runs in-process — no external server, no env vars.

## How it works

FastContext is a two-part system. You are currently reading the **skill** (instructions); the actual work is done by the **MCP server** (a Python process running the model).

```
User: "find all auth middleware"
  │
  ▼
Agent reads this SKILL.md  ──▶  decides: use fastcontext_explore
  │
  ▼
Agent calls fastcontext_explore(query="...", max_turns=4)
  │  (MCP call over stdio)
  ▼
fastcontext-mcp process
  ├─ loads FastContext-1.0-4B-mlx-4bit model
  ├─ agent loop: Read / Glob / Grep in parallel
  └─ returns file:line citations
  │
  ▼
Agent receives citations, can Read the specific lines
```

| Part | File | Role |
|------|------|------|
| Skill (this file) | `SKILL.md` | Tells the agent *when* and *how* to call the tool |
| MCP server | `fastcontext-mcp` binary | Runs the model, exposes `fastcontext_explore` as an MCP tool |

If `fastcontext_explore` is not in your tool list, the MCP server isn't installed. See the `fastcontext-setup` skill to install it.

## Prerequisite

The `fastcontext` MCP server must be registered. If the `fastcontext_explore` tool is not available, run the setup skill first — `fastcontext-setup`.

## Usage

Call the `fastcontext_explore` MCP tool directly:

```
fastcontext_explore(query="Find all authentication middleware and session handling", max_turns=4)
```

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `query` | (required) | Natural-language description of what to find |
| `max_turns` | 4 | Exploration turns (1-10) |

### When to use

- **Unfamiliar code areas**: Before editing files not yet explored
- **Cross-cutting concerns**: Finding all files related to a feature
- **Architecture discovery**: Understanding module connections
- **Dependency tracing**: Finding callers or implementors of a function
- **Before spawning exploration subagents**: A single `fastcontext_explore` call can replace many subagent Read/Glob operations. Run it first, then pass the resulting citations to subagents for targeted deep-reading — this saves tokens and wall-clock time.

### When NOT to use

- **Already-explored files**: Context is in the conversation
- **Single known file**: Direct Read is faster
- **Simple keyword search**: A single Grep suffices
- **Subagents without MCP access**: Some subagent types may not have the `fastcontext_explore` tool available. In that case, run the exploration from the main conversation first.

## Writing Effective Queries

The exploration model is a 4B parameter model — capable but sensitive to query specificity. Vague queries produce hallucinated or irrelevant citations. Specific queries produce accurate results.

### Anchor queries with concrete names

Always include at least one of: a class name, function name, filename pattern, error message, import path, or language.

| Instead of | Write |
|-----------|-------|
| "Find the main entry point" | "Find the Python file that defines the `main()` function or `console_scripts` entry point" |
| "How does auth work?" | "Find the authentication middleware classes and JWT validation logic" |
| "Find the config" | "Find `.yaml` or `.toml` config files and the Python module that loads them" |

### Mention the language or file type when known

The model searches with Glob and Grep. Mentioning `*.py`, `*.ts`, `TypeScript`, or `Go` helps it target the right files instead of guessing.

### Prefer multiple specific calls over one broad call

Split broad explorations into focused queries. Two calls at `max_turns=3` each are faster and more accurate than one call at `max_turns=6`.

```
# Instead of one broad call:
fastcontext_explore(query="Understand the entire project architecture", max_turns=6)

# Run two focused calls:
fastcontext_explore(query="Find Python entry points, CLI commands, and MCP server registration", max_turns=3)
fastcontext_explore(query="Find the LLM inference class and model loading code", max_turns=3)
```

### Verify citations before acting on them

The model may cite files that do not exist, especially on vague queries. Always Read a cited file before editing it. If a citation path looks wrong (unexpected language, framework, or directory), re-query with more specific terms.

## Query Examples

```
"Find all database migration files and the schema definition for the users table"
"Locate the API route handlers for /api/v2/users and their request validation"
"Find error handling patterns: custom error classes, error middleware, and error logging"
"Find the TypeScript React components that render the settings page and their prop types"
```

## Interpreting Results

FastContext returns citations with file paths and line ranges:

```
src/auth/middleware.ts:15-42 (JWT validation middleware)
src/auth/session.ts:8-31 (Session store implementation)
```

Use these to make targeted Read calls for the specific lines needed.

## Adjusting max_turns

- **2**: Quick lookup, single file
- **4** (default): Standard exploration
- **6-8**: Deep exploration, large codebase
- **10**: Exhaustive cross-cutting search
