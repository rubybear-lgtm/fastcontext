# fastcontext-mcp

[![CI](https://github.com/rubybear-lgtm/fastcontext/actions/workflows/ci.yml/badge.svg)](https://github.com/rubybear-lgtm/fastcontext/actions/workflows/ci.yml)
[![Release](https://github.com/rubybear-lgtm/fastcontext/actions/workflows/release.yml/badge.svg)](https://github.com/rubybear-lgtm/fastcontext/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: Apple Silicon](https://img.shields.io/badge/Platform-macOS%20Apple%20Silicon-green.svg)](#requirements)

MCP server wrapping [Microsoft FastContext](https://github.com/microsoft/fastcontext) with in-process MLX inference on Apple Silicon.

Loads the fine-tuned `rubybear/FastContext-1.0-4B-SFT-mlx-4bit-g32` model directly via `mlx_lm` — no external server, no env vars, no subprocess management. A single `fastcontext_explore` call replaces what would otherwise be many sequential Read/Glob/Grep calls.

---

## Quick start

```bash
# 1. Install the setup skill
npx add skill fastcontext-setup

# 2. In your AI coding tool (Claude Code, OpenCode, or Codex CLI), say:
#    "Install FastContext"
```

The agent follows the skill, runs the install script, and registers the MCP server with your detected tool(s). After restart, `fastcontext_explore` is available.

Prefer running the installer yourself?

```bash
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh | bash
```

## Usage

Once installed, your AI agent can call `fastcontext_explore`:

```
fastcontext_explore(query="Find all authentication middleware and session handling", max_turns=4)
```

### Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `query` | *(required)* | — | Natural-language description of what to find |
| `max_turns` | `4` | 1–10 | Exploration turns (more = deeper search) |

### Choosing `max_turns`

| Value | Use case |
|-------|----------|
| 2 | Quick lookup, single file |
| 4 *(default)* | Standard exploration |
| 6–8 | Deep exploration, large codebase |
| 10 | Exhaustive cross-cutting search |

### Example queries

```
"Find all database migration files and the schema definition for the users table"
"Locate the API route handlers for /api/v2/users and their request validation"
"Find error handling patterns: custom error classes, error middleware, and error logging"
"Locate the CLI entry point and trace the command registration pattern"
"Find all places where environment variables are read and how they're validated"
```

### What results look like

FastContext returns exploration steps and `file:line` citations:

```
## Exploration steps
- [turn 1] Glob **/*.py
- [turn 1] Grep 'def authenticate' in src/
- [turn 2] Read src/auth/middleware.py
- [turn 2] Read src/auth/session.py

## Result
src/auth/middleware.ts:15-42 (JWT validation middleware)
src/auth/session.ts:8-31 (Session store implementation)
src/auth/routes.ts:120-156 (Login route handler)
```

Use these citations to make targeted Read calls for the specific lines you need.

### When to use

- **Unfamiliar code areas** — before editing files not yet explored
- **Cross-cutting concerns** — finding all files related to a feature
- **Architecture discovery** — understanding module connections
- **Dependency tracing** — finding callers or implementors of a function

### When NOT to use

- **Already-explored files** — context is in the conversation
- **Single known file** — direct Read is faster
- **Simple keyword search** — a single Grep suffices

## Architecture

FastContext is a two-part system:

```
┌─────────────────────────────────────────────────────────────┐
│  AI agent (Claude Code / OpenCode / Codex CLI)              │
│    │                                                        │
│    ├── reads SKILL.md ──▶ knows when/how to call the tool   │
│    │                                                        │
│    └── calls fastcontext_explore ──┐                        │
│                                    │                        │
└────────────────────────────────────│────────────────────────┘
                                     │ stdio (MCP protocol)
                                     ▼
┌─────────────────────────────────────────────────────────────┐
│  fastcontext-mcp (long-running Python process)              │
│    │                                                        │
│    ├── loads FastContext-1.0-4B-mlx-4bit model into MLX     │
│    │                                                        │
│    └── agent loop: Read / Glob / Grep in parallel          │
│        returns file:line citations                          │
└─────────────────────────────────────────────────────────────┘
```

| Part | What it is | What it does |
|------|-----------|--------------|
| **MCP server** (`fastcontext-mcp`) | Python program running the 4B model via MLX | Provides the `fastcontext_explore` tool — the actual engine |
| **Skill** (`SKILL.md`) | Markdown instructions the agent loads | Tells the agent *when* and *how* to use `fastcontext_explore` |

Both are needed: the MCP server provides the tool, the skill tells the agent to use it.

## Install

### Option A: Agent-driven (recommended)

Install the setup skill, then let your agent handle the rest:

```bash
npx add skill fastcontext-setup
```

Then in your AI coding tool, say **"Install FastContext"**. The agent will:
1. Check your platform (Apple Silicon required)
2. Create a venv and install the package (prebuilt wheel by default)
3. Auto-detect which AI coding tools you have
4. Register the MCP server in the right config file(s)
5. Verify the model loads
6. Tell you to restart

### Option B: Direct install script

```bash
# Auto-detect tools, prebuilt wheel
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh | bash

# Target a specific tool
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh | bash -s -- --target claude

# Also install skill files + symlinks
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh | bash -s -- --install-skills

# Force building from git source (no prebuilt wheel)
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh | bash -s -- --from-source
```

**Flags:**

| Flag | Description |
|------|-------------|
| `--target <tool>` | `claude` \| `opencode` \| `codex` \| `both` \| `auto` (default: `auto`) |
| `--install-skills` | Also install skill files to `~/.agents/skills/` + symlink into tool dirs |
| `--from-source` | Build from git instead of downloading a prebuilt wheel |
| `--help` | Show usage |

### Option C: Manual installation

```bash
# 1. Create venv and install
uv venv ~/.cache/fastcontext/venv --python ">=3.12"
uv pip install --python ~/.cache/fastcontext/venv/bin/python "fastcontext-mcp @ git+https://github.com/rubybear-lgtm/fastcontext.git"

# 2. Register the MCP server (see Configuration below)
```

### Prebuilt wheels

Releases include a prebuilt `fastcontext_mcp-<version>-py3-none-any.whl` wheel. The install script downloads it automatically by default. To install manually:

```bash
uv pip install --python ~/.cache/fastcontext/venv/bin/python \
  https://github.com/rubybear-lgtm/fastcontext/releases/latest/download/fastcontext_mcp-0.1.0-py3-none-any.whl
```

The wheel is platform-independent (pure Python) — only the `mlx-lm` and `fastcontext` dependencies require Apple Silicon at runtime.

## Configuration

The MCP server needs to be registered with your AI coding tool. The install script handles this automatically, but for manual setup:

### Claude Code — `~/.mcp.json`

```json
{
  "mcpServers": {
    "fastcontext": {
      "command": "~/.cache/fastcontext/venv/bin/fastcontext-mcp"
    }
  }
}
```

### OpenCode — `~/.config/opencode/opencode.json`

```json
{
  "mcp": {
    "fastcontext": {
      "type": "local",
      "command": ["~/.cache/fastcontext/venv/bin/fastcontext-mcp"],
      "enabled": true
    }
  }
}
```

### Codex CLI — `~/.codex/config.toml`

```toml
[mcp_servers.fastcontext]
command = "~/.cache/fastcontext/venv/bin/fastcontext-mcp"
args = []
```

### Verifying installation

| Tool | Command |
|------|---------|
| Claude Code | `/mcp` — `fastcontext` should appear |
| OpenCode | `/mcp` or status command — `fastcontext` listed |
| Codex CLI | `codex mcp list` — `fastcontext` connected |
| Direct | `~/.cache/fastcontext/venv/bin/python -c "from fastcontext_mcp.server import mcp; print('OK')"` |

## How it works

### In-process MLX inference

The model (`rubybear/FastContext-1.0-4B-SFT-mlx-4bit-g32`, a 4-bit quantized 4B parameter model) is loaded directly into the MCP server process via `mlx_lm`. No external HTTP server, no API keys, no network calls during inference.

### KV cache reuse

The `MlxLLM` class maintains a KV cache across agent turns (`make_prompt_cache`). Each turn only prefills new tokens (tool results) instead of re-processing the entire conversation — roughly 5x speedup on subsequent turns.

### Agent loop

FastContext uses Microsoft's FastContext agent framework with three tools:
- **Read** — read file contents
- **Glob** — find files by pattern
- **Grep** — search file contents

The local model decides which tools to call and in what order, running up to `max_turns` iterations before producing a final answer with `file:line` citations.

### Project structure

```
src/fastcontext_mcp/
├── server.py        # MCP server + MlxLLM (KV-cached inference)
├── _shared.py       # Response parsing (tool call extraction)
├── configwriter.py  # MCP config + skill file installation
└── release.py       # Prebuilt wheel resolution from GitHub releases
scripts/install.sh   # One-command installer
skills/
├── fastcontext/         # Usage skill (when/how to call the tool)
└── fastcontext-setup/   # Setup skill (agent-driven installation)
benchmark/           # Benchmark harness (bench, scoring, plotting)
tests/               # Test suite (111 tests)
```

## Requirements

- **macOS with Apple Silicon** (M1/M2/M3/M4) — required for MLX
- **~5 GB free RAM** for the 4B model
- **Python ≥ 3.12**
- **`uv`** (installed automatically by the install script)

## Development

### Setup

```bash
# Clone and install in editable mode
git clone https://github.com/rubybear-lgtm/fastcontext.git
cd fastcontext
uv venv ~/.cache/fastcontext/venv --python ">=3.12"
uv pip install --python ~/.cache/fastcontext/venv/bin/python -e ".[test]"
```

### Running tests

```bash
~/.cache/fastcontext/venv/bin/python -m pytest tests/ -v
```

Tests use temporary directories and mocks — they don't touch real config files or require network access. The heavy `mlx-lm` / `fastcontext` deps aren't needed for the test suite (only the pure-Python modules: `configwriter`, `release`).

### Linting

```bash
ruff check src/fastcontext_mcp/ tests/
```

### Building a wheel

```bash
uv build --wheel
# Output: dist/fastcontext_mcp-<version>-py3-none-any.whl
```

## Releasing

Releases are automated via GitHub Actions. To cut a new release:

```bash
# Tag and push
git tag v0.1.0
git push origin v0.1.0
```

The [`release.yml`](.github/workflows/release.yml) workflow will:
1. Build the wheel
2. Verify it contains all required modules
3. Create a GitHub Release with the wheel attached
4. The install script will then automatically download it

For manual triggers, use the GitHub Actions "Run workflow" button with a version tag.

## Troubleshooting

<details>
<summary><b>Model load errors / out of memory</b></summary>

The 4B model requires ~5 GB RAM. Close memory-intensive apps. The 4-bit quantization (`-4bit-g32`) keeps memory usage minimal while preserving quality.
</details>

<details>
<summary><b>MCP server not showing after restart</b></summary>

Verify the config was written correctly:

- **Claude Code**: check `mcpServers.fastcontext` in `~/.mcp.json`
- **OpenCode**: check `mcp.fastcontext` in `~/.config/opencode/opencode.json`
- **Codex CLI**: check `[mcp_servers.fastcontext]` in `~/.codex/config.toml`

Re-run the install script with `--target <tool>` if needed.
</details>

<details>
<summary><b>Import errors</b></summary>

Check the underlying error:

```bash
~/.cache/fastcontext/venv/bin/python -c "from fastcontext_mcp.server import mcp; print('OK')"
```

Common causes: missing `uv`, wrong Python version (< 3.12), or corrupted venv. Delete `~/.cache/fastcontext/venv` and re-run the installer.
</details>

<details>
<summary><b>First call to fastcontext_explore is slow</b></summary>

This is normal — the model loads into memory on first use (~10-30 seconds). Subsequent calls reuse the loaded model. The KV cache also warms up after the first turn within a single exploration.
</details>

<details>
<summary><b>Prebuilt wheel download fails</b></summary>

The install script automatically falls back to building from git source. To force source builds, use `--from-source`. To check available releases, visit the [releases page](https://github.com/rubybear-lgtm/fastcontext/releases).
</details>

## License

MIT
