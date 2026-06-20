# fastcontext-mcp

MCP server wrapping [Microsoft FastContext](https://github.com/microsoft/fastcontext) with in-process MLX inference on Apple Silicon.

Loads the fine-tuned `rubybear/FastContext-1.0-4B-SFT-mlx-4bit-g32` model directly via `mlx_lm` — no external server, no env vars, no subprocess management.

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

### One-command install (recommended)

Install the setup skill, then ask your agent to install the MCP server:

```bash
npx add skill fastcontext-setup
```

Then in your AI coding tool, say:

> Install FastContext

The agent will follow the skill instructions, run the install script, register the MCP server with your detected tool(s), and tell you to restart.

### Direct install

If you prefer to run the install script yourself:

```bash
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh | bash
```

Target a specific tool with `--target claude|opencode|codex|both` (default: auto-detect).

### What the install script does

1. Ensures `uv` is available (installs if missing)
2. Creates a venv at `~/.cache/fastcontext/venv` and installs `fastcontext-mcp`
   - **Default**: downloads a prebuilt wheel from the latest GitHub release (fast — no git clone)
   - **Fallback**: if no release exists, builds from the git repo
   - **`--from-source`**: skip the prebuilt check and always build from git
3. Auto-detects installed AI coding tools (or uses explicit `--target`)
4. Registers the MCP server in the appropriate config file(s):
   - Claude Code → `~/.mcp.json`
   - OpenCode → `~/.config/opencode/opencode.json`
   - Codex CLI → `~/.codex/config.toml`
5. Verifies the model loads correctly

With `--install-skills`, also downloads and installs the FastContext skill files (`fastcontext`, `fastcontext-setup`) to `~/.agents/skills/` and symlinks them into detected tool skill directories.

After installation, **restart your AI coding tool**. The `fastcontext_explore` MCP tool becomes available automatically.

### Prebuilt wheels

Releases include a prebuilt `fastcontext_mcp-<version>-py3-none-any.whl` wheel. The install script downloads it automatically by default. To install it manually:

```bash
# Download from the latest release (replace <version> accordingly)
uv pip install --python ~/.cache/fastcontext/venv/bin/python \
  https://github.com/rubybear-lgtm/fastcontext/releases/latest/download/fastcontext_mcp-0.1.0-py3-none-any.whl
```

The wheel is platform-independent (pure Python) — only the `mlx-lm` and `fastcontext` dependencies require Apple Silicon at runtime.

### Manual installation

```bash
uv venv ~/.cache/fastcontext/venv --python ">=3.12"
uv pip install --python ~/.cache/fastcontext/venv/bin/python "fastcontext-mcp @ git+https://github.com/rubybear-lgtm/fastcontext.git"
```

Then register the MCP server manually — see [`skills/fastcontext-setup/SKILL.md`](skills/fastcontext-setup/SKILL.md) for the per-tool config snippets.

## Run

```bash
fastcontext-mcp
```

## Requirements

- macOS with Apple Silicon (M1/M2/M3/M4) — required for MLX
- ~5 GB free RAM for the 4B model
- Python ≥ 3.12

## License

MIT
