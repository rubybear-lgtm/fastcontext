#!/bin/bash
# Install fastcontext-mcp: create venv, install package, register MCP server, verify.
set -euo pipefail

VENV_DIR="${HOME}/.cache/fastcontext/venv"
REPO_URL="git+https://github.com/rubybear-lgtm/fastcontext.git"

# Parse --target flag: claude | opencode | both
# Default: auto-detect (both if tools found, claude as fallback)
TARGET="auto"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --target) TARGET="$2"; shift 2 ;;
        --target=*) TARGET="${1#*=}"; shift ;;
        *) echo "Unknown flag: $1"; exit 1 ;;
    esac
done

echo "=== fastcontext-mcp installer ==="

# -------------------------------------------------------------------
# 1. Ensure uv
# -------------------------------------------------------------------
if ! command -v uv &> /dev/null; then
    echo "[1/5] Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
echo "[1/5] uv $(uv --version | awk '{print $2}') OK"

# -------------------------------------------------------------------
# 2. Create venv and install package
# -------------------------------------------------------------------
echo "[2/5] Installing fastcontext-mcp..."
if [ ! -d "$VENV_DIR" ]; then
    uv venv "$VENV_DIR" --python ">=3.12" --quiet
fi
PYTHON="$VENV_DIR/bin/python"
uv pip install --quiet --python "$PYTHON" "fastcontext-mcp @ $REPO_URL"
echo "      Installed into $VENV_DIR"

# -------------------------------------------------------------------
# 3. Determine which tools to register with
# -------------------------------------------------------------------
echo "[3/5] Detecting tools..."

has_claude() { [ -d "${HOME}/.claude" ] || command -v claude &>/dev/null; }
has_opencode() { [ -d "${HOME}/.config/opencode" ] || command -v opencode &>/dev/null; }

REGISTER_CLAUDE=false
REGISTER_OPENCODE=false

case "$TARGET" in
    claude)
        REGISTER_CLAUDE=true ;;
    opencode)
        REGISTER_OPENCODE=true ;;
    both)
        REGISTER_CLAUDE=true
        REGISTER_OPENCODE=true ;;
    auto)
        if has_claude; then REGISTER_CLAUDE=true; fi
        if has_opencode; then REGISTER_OPENCODE=true; fi
        # Fallback: if nothing detected, default to claude
        if ! $REGISTER_CLAUDE && ! $REGISTER_OPENCODE; then
            REGISTER_CLAUDE=true
        fi
        ;;
    *)
        echo "Unknown --target: $TARGET (use claude, opencode, both, or auto)"
        exit 1 ;;
esac

echo "      Claude Code: $REGISTER_CLAUDE"
echo "      OpenCode:    $REGISTER_OPENCODE"

# -------------------------------------------------------------------
# 4. Register MCP servers
# -------------------------------------------------------------------
echo "[4/5] Registering MCP server(s)..."

"$PYTHON" -c "
import json, os
from pathlib import Path

venv = os.environ['VENV_DIR']
command_path = f'{venv}/bin/fastcontext-mcp'

# --- Claude Code (~/.mcp.json) ---
if '$REGISTER_CLAUDE' == 'true':
    path = Path.home() / '.mcp.json'
    if path.exists():
        config = json.loads(path.read_text())
    else:
        config = {}
    if 'mcpServers' not in config:
        config['mcpServers'] = {}
    if 'fastcontext' in config['mcpServers']:
        print('      Claude Code: already registered.')
    else:
        config['mcpServers']['fastcontext'] = {
            'command': command_path,
            'args': [],
        }
        path.write_text(json.dumps(config, indent=2) + '\n')
        print(f'      Claude Code: added to {path}')

# --- OpenCode (~/.config/opencode/opencode.json) ---
if '$REGISTER_OPENCODE' == 'true':
    path = Path.home() / '.config' / 'opencode' / 'opencode.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        config = json.loads(path.read_text())
    else:
        config = {}
    if 'mcp' not in config:
        config['mcp'] = {}
    if 'fastcontext' in config['mcp']:
        print('      OpenCode: already registered.')
    else:
        config['mcp']['fastcontext'] = {
            'type': 'local',
            'command': [command_path],
            'enabled': True,
        }
        path.write_text(json.dumps(config, indent=2) + '\n')
        print(f'      OpenCode: added to {path}')
"

# -------------------------------------------------------------------
# 5. Verify
# -------------------------------------------------------------------
echo "[5/5] Verifying..."
"$PYTHON" -c "
from fastcontext_mcp.server import mcp
print('      MCP server loads OK.')
print('      Model loaded in-process.')
"

echo ""
echo "=== Done ==="
echo "  Server: $VENV_DIR/bin/fastcontext-mcp"
if $REGISTER_CLAUDE; then
    echo "  MCP:    Registered in ~/.mcp.json (Claude Code)"
fi
if $REGISTER_OPENCODE; then
    echo "  MCP:    Registered in ~/.config/opencode/opencode.json (OpenCode)"
fi
echo ""
echo "Restart your AI coding tool to activate the MCP server."
