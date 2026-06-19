---
name: fastcontext-setup
description: This skill should be used when the user asks to "install FastContext", "set up FastContext", "configure FastContext MCP", "add FastContext", or mentions needing to install or configure the FastContext exploration agent. Installs the MCP server, registers it with Claude Code, and verifies the setup.
---

# FastContext Setup

Install and configure fastcontext-mcp — an MCP server that runs Microsoft FastContext with in-process MLX inference on Apple Silicon.

## Prerequisites

- macOS with Apple Silicon (M1/M2/M3/M4)
- `uv` (installed automatically if missing)

## Installation

Run the bundled install script. It creates a venv, installs the package (including the MLX model), registers the MCP server in Claude Code settings, and verifies everything works:

```bash
bash "$(dirname "$(find ~/.claude/skills ~/.agents/skills .claude/skills -name 'SKILL.md' -path '*setup*' -path '*fastcontext*' 2>/dev/null | head -1)")/../../scripts/install.sh"
```

The script performs:
1. Ensures `uv` is available
2. Creates a venv at `~/.cache/fastcontext/venv` and installs `fastcontext-mcp`
3. Registers the MCP server in `~/.claude/settings.json`
4. Verifies the model loads correctly

After installation, restart Claude Code. The `fastcontext_explore` MCP tool becomes available automatically.

## Manual Installation

If the automated script is not suitable:

```bash
uv venv ~/.cache/fastcontext/venv --python ">=3.12"
uv pip install --python ~/.cache/fastcontext/venv/bin/python "fastcontext-mcp @ git+https://github.com/rubybear-lgtm/fastcontext.git"
```

Then add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "fastcontext": {
      "command": "~/.cache/fastcontext/venv/bin/fastcontext-mcp"
    }
  }
}
```

## Verification

After restarting Claude Code, run `/mcp` to confirm the `fastcontext` server appears.

## Troubleshooting

- **Model load errors**: The 4B model requires ~5 GB RAM. Close memory-intensive apps.
- **Import errors**: Run `~/.cache/fastcontext/venv/bin/python -c "from fastcontext_mcp.server import mcp"` to check.
- **MCP not showing**: Verify `mcpServers.fastcontext` exists in `~/.claude/settings.json` and restart Claude Code.
