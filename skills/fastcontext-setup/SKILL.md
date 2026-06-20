---
name: fastcontext-setup
description: This skill should be used when the user asks to "install FastContext", "set up FastContext", "configure FastContext MCP", "add FastContext", or mentions needing to install or configure the FastContext exploration agent. Installs the MCP server, registers it with the user's AI coding tool, and verifies the setup.
---

# FastContext Setup

Install and configure fastcontext-mcp — an MCP server that runs Microsoft FastContext for parallel codebase exploration. Uses a local MLX model on Apple Silicon for in-process inference (no external API calls).

## Prerequisites

- macOS with Apple Silicon (M1/M2/M3/M4) — required for MLX
- `uv` (installed automatically if missing)

## Installation

### Quick install

Run the install script directly from the repo:

```bash
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh | bash
```

The script auto-detects which AI coding tools you have installed and registers the MCP server accordingly. To target specific tools:

```bash
# Claude Code only
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh | bash -s -- --target claude

# OpenCode only
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh | bash -s -- --target opencode

# Both
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh | bash -s -- --target both
```

### What the script does

1. Ensures `uv` is available
2. Creates a venv at `~/.cache/fastcontext/venv` and installs `fastcontext-mcp`
3. Auto-detects installed AI coding tools (or uses explicit `--target`)
4. Registers the MCP server in the appropriate config file(s)
5. Verifies the model loads correctly

After installation, restart your AI coding tool. The `fastcontext_explore` MCP tool becomes available automatically.

### Manual installation

If the automated script is not suitable:

```bash
uv venv ~/.cache/fastcontext/venv --python ">=3.12"
uv pip install --python ~/.cache/fastcontext/venv/bin/python "fastcontext-mcp @ git+https://github.com/rubybear-lgtm/fastcontext.git"
```

Then register the MCP server manually:

**Claude Code** — add to `~/.mcp.json`:
```json
{
  "mcpServers": {
    "fastcontext": {
      "command": "~/.cache/fastcontext/venv/bin/fastcontext-mcp"
    }
  }
}
```

**OpenCode** — add to `~/.config/opencode/opencode.json` under the `mcp` key:
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

## Verification

- **Claude Code**: Run `/mcp` to confirm the `fastcontext` server appears in the list.
- **OpenCode**: Check that `fastcontext` appears in the MCP servers list (use `/mcp` or the equivalent status command).

You can also verify directly:
```bash
~/.cache/fastcontext/venv/bin/python -c "from fastcontext_mcp.server import mcp; print('OK')"
```

## Troubleshooting

- **Model load errors**: The 4B model requires ~5 GB RAM. Close memory-intensive apps.
- **Import errors**: Run the verification command above to check Python dependencies.
- **MCP not showing**: Verify the config was written correctly and restart your tool.
  - Claude Code: check `mcpServers.fastcontext` in `~/.mcp.json`
  - OpenCode: check `mcp.fastcontext` in `~/.config/opencode/opencode.json`
- **Wrong tool registered**: Re-run with `--target` to specify which tool(s) to configure.
