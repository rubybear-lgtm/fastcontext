---
name: fastcontext
description: This skill should be used when the user asks to "explore the codebase", "find related files", "understand the architecture", "search for implementations", "use FastContext", or when broad codebase context is needed before editing unfamiliar code. Runs Microsoft FastContext — a parallel exploration agent — locally on Apple Silicon via MLX for efficient file-line citation retrieval.
---

# FastContext

FastContext is a specialized exploration agent that runs Read, Glob, and Grep operations in parallel using a dedicated local LLM, returning compact file-path:line-range citations. It reduces main-agent token consumption by up to 60% compared to manual exploration.

This skill runs the fine-tuned `mattrobenolt/FastContext-1.0-4B-SFT-mlx-bf16` model locally on Apple Silicon via MLX. No API keys or external services needed.

**Automatic enforcement**: A PreToolUse hook intercepts exploratory Read/Grep/Glob calls and redirects them to FastContext. Targeted reads of specific known files are allowed through. This is configured automatically by the installer.

## First-Time Setup

Before first use, check if FastContext is installed. Run this verification:

```bash
~/.cache/fastcontext/venv/bin/python -c "from fastcontext.agent.agent_factory import make_fastcontext_agent; import mlx_lm; print('OK')" 2>&1
```

If it prints `OK`, skip to **Ensure MLX Server**. If the venv or imports fail, run the installer:

```bash
bash "$(dirname "$(find ~/.claude/skills ~/.agents/skills .claude/skills -name 'SKILL.md' -path '*fastcontext*' 2>/dev/null | head -1)")/scripts/install.sh"
```

The installer uses `uv` to create a venv at `~/.cache/fastcontext/venv`, installs `fastcontext` and `mlx-lm`, downloads the model (~2.5 GB), and symlinks the `fastcontext` CLI to `~/.local/bin/`. Takes 2-5 minutes on first run.

## Ensure MLX Server

Before running FastContext, ensure the MLX LM server is running. Check and start it:

```bash
python3 "$(dirname "$(find ~/.claude/skills ~/.agents/skills .claude/skills -name 'SKILL.md' -path '*fastcontext*' 2>/dev/null | head -1)")/scripts/ensure-mlx.py"
```

This script checks if `localhost:8080` is responding. If not, it starts the MLX server as a background daemon. The server persists across sessions — start it once and it serves all future FastContext calls.

## Running FastContext

Execute exploration queries using the FastContext CLI:

```bash
fastcontext --query "QUERY_HERE" --max-turns 4 --citation
```

### Parameters

| Flag | Default | Description |
|------|---------|-------------|
| `--query`, `-q` | (required) | Natural-language exploration request |
| `--max-turns` | 4 | Maximum exploration turns (1-10) |
| `--citation` | false | Return only the `<final_answer>` citation block |
| `--verbose` | false | Print intermediate agent messages |

### Example queries

```bash
# Find auth-related code
fastcontext -q "Find all authentication middleware, session handling, and token validation" --max-turns 4 --citation

# Trace a feature
fastcontext -q "Locate the API route handlers for /api/users and their request validation logic" --max-turns 6 --citation

# Understand architecture
fastcontext -q "Find the database models, migration files, and ORM configuration" --max-turns 4 --citation
```

## When to Use FastContext

### Ideal scenarios

- **Unfamiliar code areas**: Before editing files in an area not yet explored in the session
- **Cross-cutting concerns**: Finding all files related to a feature (auth, logging, error handling)
- **Architecture discovery**: Understanding how modules connect, where interfaces are defined
- **Dependency tracing**: Finding callers, implementors, or consumers of a function/type
- **Pre-edit context gathering**: Building understanding before making a change

### When NOT to use

- **Already-explored files**: Context is already in the conversation
- **Single known file**: Direct Read is faster for a specific file
- **Simple grep**: A single Grep call suffices for a keyword search

## Writing Effective Queries

**Be specific about what to find:**
- "Find all database migration files and the schema definition for the users table"
- "Locate error handling patterns: custom error classes, error middleware, and error logging"

**Include structural hints:**
- "Find the React components that render the dashboard, including their data fetching hooks"
- "Locate the CLI entry point and trace the command registration pattern"

**Avoid vague queries:**
- "Find interesting code" — too broad
- "Show me everything" — unfocused

## Interpreting Results

FastContext returns citations with file paths and line ranges:

```
src/auth/middleware.ts:15-42 — JWT validation middleware
src/auth/session.ts:8-31 — Session store implementation
src/routes/auth.ts:55-89 — Login/logout route handlers
```

Use these citations to make targeted Read calls for the specific lines needed before editing.

## Adjusting max_turns

- **2 turns**: Quick lookup, single file or pattern
- **4 turns** (default): Standard exploration, multiple related files
- **6-8 turns**: Deep exploration across a large codebase
- **10 turns**: Exhaustive search for complex cross-cutting concerns

## Workflow Integration

1. Identify the area to modify
2. Run `fastcontext --query "..." --citation` to gather context
3. Review the returned citations
4. Read specific cited line ranges for detailed understanding
5. Make targeted edits with full context

This replaces the slower pattern of issuing many sequential Read/Glob/Grep calls.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL` | `mattrobenolt/FastContext-1.0-4B-SFT-mlx-bf16` | MLX model to serve |
| `BASE_URL` | `http://localhost:8080/v1` | LLM endpoint URL |
| `API_KEY` | `no-key-needed` | API key (not needed for local MLX) |

Override these to use a different model or remote endpoint.

## Troubleshooting

For detailed troubleshooting, see **`references/troubleshooting.md`**.

Quick checks:
- **Import errors**: `python3 -c "import fastcontext; import mlx_lm"` — re-run install.sh if it fails
- **MLX server not responding**: `curl http://localhost:8080/v1/models` — re-run ensure-mlx.py
- **Server logs**: `cat ~/.cache/fastcontext/mlx-server.log`
