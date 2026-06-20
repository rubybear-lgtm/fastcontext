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
has_codex() { command -v codex &>/dev/null; }

REGISTER_TOOLS=()

case "$TARGET" in
    claude)   REGISTER_TOOLS=(claude) ;;
    opencode) REGISTER_TOOLS=(opencode) ;;
    codex)    REGISTER_TOOLS=(codex) ;;
    both)     REGISTER_TOOLS=(claude opencode codex) ;;
    auto)
        has_claude   && REGISTER_TOOLS+=(claude)
        has_opencode && REGISTER_TOOLS+=(opencode)
        has_codex    && REGISTER_TOOLS+=(codex)
        # Fallback: if nothing detected, default to claude
        if [ ${#REGISTER_TOOLS[@]} -eq 0 ]; then
            REGISTER_TOOLS=(claude)
        fi
        ;;
    *)
        echo "Unknown --target: $TARGET (use claude, opencode, codex, both, or auto)"
        exit 1 ;;
esac

echo "      Tools to register: ${REGISTER_TOOLS[*]:-(none)}"

# -------------------------------------------------------------------
# 4. Register MCP servers
# -------------------------------------------------------------------
echo "[4/5] Registering MCP server(s)..."

export VENV_DIR

"$PYTHON" -c "
import json, os, sys, tomllib
from pathlib import Path

try:
    import tomli_w
except ImportError:
    print('      Installing tomli-w for TOML support...')
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--quiet', 'tomli-w>=1.2.0'])
    import tomli_w

venv = os.environ['VENV_DIR']
command_path = f'{venv}/bin/fastcontext-mcp'
tools_str = '${REGISTER_TOOLS[*]}'.strip()
tools = tools_str.split() if tools_str else []

TOOLS = {
    'claude': {
        'path': Path.home() / '.mcp.json',
        'format': 'json',
        'container_key': 'mcpServers',
        'entry_name': 'fastcontext',
        'entry': {'command': command_path, 'args': []},
    },
    'opencode': {
        'path': Path.home() / '.config' / 'opencode' / 'opencode.json',
        'format': 'json',
        'container_key': 'mcp',
        'entry_name': 'fastcontext',
        'entry': {'type': 'local', 'command': [command_path], 'enabled': True},
    },
    'codex': {
        'path': Path.home() / '.codex' / 'config.toml',
        'format': 'toml',
        'container_key': 'mcp_servers',
        'entry_name': 'fastcontext',
        'entry': {'command': command_path, 'args': []},
    },
}

def _ensure_json(path, container_key, entry_name, entry):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        content = path.read_text().strip()
        config = json.loads(content) if content else {}
    else:
        config = {}
    config.setdefault(container_key, {})
    if entry_name in config[container_key]:
        print(f'      {path}: already registered.')
        return False
    config[container_key][entry_name] = entry
    path.write_text(json.dumps(config, indent=2) + '\n')
    print(f'      Added to {path}')
    return True

def _ensure_toml(path, container_key, entry_name, entry):
    if path.exists():
        config = tomllib.loads(path.read_text())
    else:
        config = {}
    config.setdefault(container_key, {})
    if entry_name in config[container_key]:
        print(f'      {path}: already registered.')
        return False
    config[container_key][entry_name] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(config))
    print(f'      Added to {path}')
    return True

if not tools:
    print('      No tools to register.')
else:
    for tool_name in tools:
        if tool_name not in TOOLS:
            print(f'      Unknown tool: {tool_name}, skipping.')
            continue
        cfg = TOOLS[tool_name]
        if cfg['format'] == 'json':
            _ensure_json(cfg['path'], cfg['container_key'], cfg['entry_name'], cfg['entry'])
        elif cfg['format'] == 'toml':
            _ensure_toml(cfg['path'], cfg['container_key'], cfg['entry_name'], cfg['entry'])
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
for tool in "${REGISTER_TOOLS[@]}"; do
    case "$tool" in
        claude)   echo "  MCP:    Registered in ~/.mcp.json (Claude Code)" ;;
        opencode) echo "  MCP:    Registered in ~/.config/opencode/opencode.json (OpenCode)" ;;
        codex)    echo "  MCP:    Registered in ~/.codex/config.toml (Codex CLI)" ;;
    esac
done
echo ""
echo "Restart your AI coding tool to activate the MCP server."
