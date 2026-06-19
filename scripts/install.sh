#!/bin/bash
# Install fastcontext-mcp: create venv, install package, register MCP server, verify.
set -euo pipefail

VENV_DIR="${HOME}/.cache/fastcontext/venv"
REPO_URL="git+https://github.com/rubybear-lgtm/fastcontext.git"

echo "=== fastcontext-mcp installer ==="

# -------------------------------------------------------------------
# 1. Ensure uv
# -------------------------------------------------------------------
if ! command -v uv &> /dev/null; then
    echo "[1/4] Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
echo "[1/4] uv $(uv --version | awk '{print $2}') OK"

# -------------------------------------------------------------------
# 2. Create venv and install package
# -------------------------------------------------------------------
echo "[2/4] Installing fastcontext-mcp..."
if [ ! -d "$VENV_DIR" ]; then
    uv venv "$VENV_DIR" --python ">=3.12" --quiet
fi
PYTHON="$VENV_DIR/bin/python"
uv pip install --quiet --python "$PYTHON" "fastcontext-mcp @ $REPO_URL"
echo "      Installed into $VENV_DIR"

# -------------------------------------------------------------------
# 3. Register MCP server in Claude Code settings
# -------------------------------------------------------------------
echo "[3/4] Registering MCP server..."
MCP_FILE="${HOME}/.mcp.json"

"$PYTHON" -c "
import json
from pathlib import Path

path = Path('$MCP_FILE')
venv = '$VENV_DIR'

if path.exists():
    with open(path) as f:
        config = json.load(f)
else:
    config = {}

if 'mcpServers' not in config:
    config['mcpServers'] = {}

if 'fastcontext' in config['mcpServers']:
    print('      MCP server already registered.')
else:
    config['mcpServers']['fastcontext'] = {
        'command': f'{venv}/bin/fastcontext-mcp',
        'args': [],
    }
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)
    print('      MCP server added to', str(path))
"

# -------------------------------------------------------------------
# 4. Verify
# -------------------------------------------------------------------
echo "[4/4] Verifying..."
"$PYTHON" -c "
from fastcontext_mcp.server import mcp
print('      MCP server loads OK.')
print('      Model loaded in-process.')
"

echo ""
echo "=== Done ==="
echo "  Server: $VENV_DIR/bin/fastcontext-mcp"
echo "  MCP:    Registered in ~/.mcp.json"
echo ""
echo "Restart Claude Code to activate the MCP server."
