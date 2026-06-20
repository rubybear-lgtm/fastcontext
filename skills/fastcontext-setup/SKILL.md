---
name: fastcontext-setup
description: This skill should be used when the user asks to "install FastContext", "set up FastContext", "configure FastContext MCP", "add FastContext", or mentions needing to install or configure the FastContext exploration agent. Installs the MCP server, registers it with the user's AI coding tool, and verifies the setup.
---

# FastContext Setup

Install and configure `fastcontext-mcp` — an MCP server that runs Microsoft FastContext for parallel codebase exploration. Uses a local MLX model on Apple Silicon for in-process inference (no external API calls).

## Architecture (why two parts)

FastContext has two components that must both be present:

| Component | What it is | What it does |
|-----------|-----------|--------------|
| **MCP server** | A Python program (`fastcontext-mcp`) running the `FastContext-1.0-4B` model via MLX | Provides the `fastcontext_explore` tool — the actual engine |
| **Skill** (this file) | Instructions the AI agent loads | Tells the agent *when* and *how* to use `fastcontext_explore` |

The skill is easy to install (`npx skills add rubybear-lgtm/fastcontext@fastcontext-setup -g -y`) — it's just a Markdown file. The MCP server is harder: it requires a Python venv, a model download, and registration in your agent tool's config file. **This skill exists to bridge that gap** — it lets the agent install the MCP server for the user instead of requiring the user to do it manually.

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

## Prerequisites

- macOS with Apple Silicon (M1/M2/M3/M4) — required for MLX
- ~5 GB free RAM for the 4B model
- `uv` (installed automatically if missing)

## Installation procedure (agent-executed)

**You (the AI agent) should perform these steps yourself using bash.** Do not just print these commands for the user to paste — execute them and report the results. Pause only to ask permission before the first command that modifies the system (the install script).

### Step 1: Guard check

Verify the user is on macOS Apple Silicon. Run:

```bash
uname -s && uname -m
```

- `Darwin` + `arm64` → proceed
- Anything else → stop and tell the user: "FastContext requires macOS with Apple Silicon (M-series) for MLX inference. Your platform is <uname -s> <uname -m>." Do not continue.

### Step 2: Check if already installed

```bash
test -x "$HOME/.cache/fastcontext/venv/bin/fastcontext-mcp" && echo INSTALLED || echo NOT_INSTALLED
```

- `INSTALLED` → skip to **Step 5: Verify** (the MCP is already there; only config registration might be missing, which the install script will detect idempotently).
- `NOT_INSTALLED` → continue.

### Step 3: Ask permission

Tell the user:

> "I'll install fastcontext-mcp now. This will:
> - Create a Python venv at `~/.cache/fastcontext/venv`
> - Download the `FastContext-1.0-4B-mlx-4bit` model (~2 GB on first use)
> - Register the MCP server with your detected AI coding tool(s)
>
> Shall I proceed?"

Wait for an affirmative response before running the next command.

### Step 4: Run the install script

The repo's `scripts/install.sh` handles everything: uv bootstrap, venv creation, package install, agent-tool auto-detection, MCP config registration, and verification. By default it downloads a **prebuilt wheel** from the latest GitHub release (fast — no git clone) and falls back to building from source if no release exists. Run it directly from GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh | bash
```

To target a specific tool, pass `--target`:

```bash
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh | bash -s -- --target claude
# alternatives: --target opencode | --target codex | --target both
```

To also install the FastContext skill files (`fastcontext` and `fastcontext-setup`) to `~/.agents/skills/` and symlink them into your tool's skill directory, add `--install-skills`:

```bash
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh | bash -s -- --install-skills
```

To force building from git source instead of the prebuilt wheel, add `--from-source`:

```bash
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh | bash -s -- --from-source
```

To update to the latest version (re-installs the package, keeps config registrations):

```bash
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh | bash -s -- --update
```

To uninstall (removes the venv, MCP config entries, and skill files):

```bash
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh | bash -s -- --uninstall
```

The script is idempotent and safe to re-run. It prints a `=== Done ===` block at the end listing which config files were written.

If the script fails, capture the output and report the failing step to the user. Common failures:
- `uv` install failed → network issue; retry or install uv manually from https://astral.sh/uv
- `uv pip install` failed → check network / disk space; the model is ~2 GB
- Config write failed → likely a permissions issue on the config file; report the path

### Step 5: Verify

Run the install script's own verification step:

```bash
"$HOME/.cache/fastcontext/venv/bin/python" -c "from fastcontext_mcp.server import mcp; print('MCP server loads OK')"
```

- Success → continue to Step 6
- Failure → report the error to the user and suggest re-running the install script

Also check that the MCP config entry exists for the tool(s) the user uses:

```bash
# Claude Code
grep -q '"fastcontext"' "$HOME/.mcp.json" 2>/dev/null && echo "claude: registered" || echo "claude: not registered"

# OpenCode
grep -q '"fastcontext"' "$HOME/.config/opencode/opencode.json" 2>/dev/null && echo "opencode: registered" || echo "opencode: not registered"

# Codex CLI
grep -q 'fastcontext' "$HOME/.codex/config.toml" 2>/dev/null && echo "codex: registered" || echo "codex: not registered"
```

If a tool the user uses shows "not registered", re-run the install script with `--target <tool>`.

### Step 6: Report and instruct restart

Report to the user:
- Which venv was created (path)
- Which agent tool config(s) were written (paths)
- That verification passed

Then tell them the final manual step:

> **Restart your AI coding tool now** for the `fastcontext_explore` MCP tool to become available. After restart, you can ask me to explore the codebase and I'll use FastContext automatically.

## Manual installation (fallback)

If the automated procedure above is not suitable (e.g. sandboxed environment, no network access for `curl`, or the user prefers manual control), share these steps with the user:

```bash
# 1. Ensure uv (https://astral.sh/uv)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Create venv and install
uv venv ~/.cache/fastcontext/venv --python ">=3.12"
uv pip install --python ~/.cache/fastcontext/venv/bin/python "fastcontext-mcp @ git+https://github.com/rubybear-lgtm/fastcontext.git"
```

Then register the MCP server manually in the relevant config file:

**Claude Code** — `~/.mcp.json`:
```json
{
  "mcpServers": {
    "fastcontext": {
      "command": "~/.cache/fastcontext/venv/bin/fastcontext-mcp"
    }
  }
}
```

**OpenCode** — `~/.config/opencode/opencode.json` under the `mcp` key:
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

**Codex CLI** — `~/.codex/config.toml`:
```toml
[mcp_servers.fastcontext]
command = "~/.cache/fastcontext/venv/bin/fastcontext-mcp"
args = []
```

## Verification commands for the user

After restarting their tool, the user can confirm with:

- **Claude Code**: `/mcp` → `fastcontext` should be in the list
- **OpenCode**: `/mcp` or the equivalent status command → `fastcontext` listed
- **Codex CLI**: `codex mcp list` → `fastcontext` connected

## Troubleshooting

- **Model load errors**: The 4B model requires ~5 GB RAM. Close memory-intensive apps.
- **Import errors**: Run `~/.cache/fastcontext/venv/bin/python -c "from fastcontext_mcp.server import mcp; print('OK')"` to see the underlying error.
- **MCP not showing after restart**: Verify the config was written correctly:
  - Claude Code: `mcpServers.fastcontext` in `~/.mcp.json`
  - OpenCode: `mcp.fastcontext` in `~/.config/opencode/opencode.json`
  - Codex CLI: `[mcp_servers.fastcontext]` in `~/.codex/config.toml`
- **Wrong tool registered**: Re-run the install script with `--target <claude|opencode|codex|both>`.
- **First call to `fastcontext_explore` is slow**: This is normal — the model is loading into memory on first use. Subsequent calls reuse the loaded model.
