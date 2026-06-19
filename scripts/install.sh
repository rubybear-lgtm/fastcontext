#!/bin/bash
# Install FastContext and all dependencies, download the MLX model,
# configure hooks, and verify end-to-end.
# Uses uv for virtual environment management.
set -euo pipefail

MODEL="${MODEL:-mattrobenolt/FastContext-1.0-4B-SFT-mlx-bf16}"
VENV_DIR="${HOME}/.cache/fastcontext/venv"
BIN_DIR="${HOME}/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== FastContext Installer ==="

# -------------------------------------------------------------------
# 1. Check for uv
# -------------------------------------------------------------------
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
echo "[1/8] uv $(uv --version | awk '{print $2}') OK"

# -------------------------------------------------------------------
# 2. Create virtual environment with Python 3.12+
# -------------------------------------------------------------------
echo "[2/8] Setting up virtual environment at $VENV_DIR..."
uv venv "$VENV_DIR" --python ">=3.12" --quiet
PYTHON="$VENV_DIR/bin/python"
echo "      Python $($PYTHON --version | awk '{print $2}') in venv"

# -------------------------------------------------------------------
# 3. Install packages
# -------------------------------------------------------------------
echo "[3/8] Installing packages..."
uv pip install --quiet --python "$PYTHON" mlx-lm
uv pip install --quiet --python "$PYTHON" "git+https://github.com/microsoft/fastcontext.git"
echo "      Packages installed."

# -------------------------------------------------------------------
# 4. Verify imports
# -------------------------------------------------------------------
echo "[4/8] Verifying imports..."
"$PYTHON" -c "
from fastcontext.agent.agent_factory import make_fastcontext_agent
import mlx_lm
print('      All imports OK.')
"

# -------------------------------------------------------------------
# 5. Create wrapper CLI with baked-in defaults
# -------------------------------------------------------------------
echo "[5/8] Creating CLI wrapper..."
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/fastcontext" << 'WRAPPER'
#!/bin/bash
# FastContext CLI wrapper — applies defaults so the upstream CLI
# doesn't crash on missing env vars.
export MODEL="${MODEL:-mattrobenolt/FastContext-1.0-4B-SFT-mlx-bf16}"
export API_KEY="${API_KEY:-no-key-needed}"
export BASE_URL="${BASE_URL:-http://localhost:8080/v1}"
exec "$HOME/.cache/fastcontext/venv/bin/fastcontext" "$@"
WRAPPER
chmod +x "$BIN_DIR/fastcontext"
echo "      $BIN_DIR/fastcontext (wrapper with defaults)"

# -------------------------------------------------------------------
# 6. Download model
# -------------------------------------------------------------------
echo "[6/8] Downloading model: $MODEL (this may take a few minutes on first run)..."
"$PYTHON" -c "
from huggingface_hub import snapshot_download
path = snapshot_download('$MODEL')
print(f'      Model cached at: {path}')
"

# -------------------------------------------------------------------
# 7. End-to-end smoke test
# -------------------------------------------------------------------
echo "[7/8] Smoke test..."

# Start MLX server if not running
"$PYTHON" "$SCRIPT_DIR/ensure-mlx.py" 2>&1 | sed 's/^/      /'

# Run a real fastcontext query
SMOKE_OUTPUT=$("$BIN_DIR/fastcontext" --query "List the files in this directory" --max-turns 1 --citation 2>&1) || true
if echo "$SMOKE_OUTPUT" | grep -q "final_answer\|No final answer"; then
    echo "      End-to-end test passed."
else
    echo "      WARNING: Smoke test returned unexpected output:"
    echo "$SMOKE_OUTPUT" | head -5 | sed 's/^/      /'
    echo "      FastContext may not be working correctly. Check troubleshooting docs."
fi

# -------------------------------------------------------------------
# 8. Install PreToolUse hook into Claude Code settings
# -------------------------------------------------------------------
echo "[8/8] Configuring hooks..."
SETTINGS_FILE="${HOME}/.claude/settings.json"

if [ -f "$SETTINGS_FILE" ]; then
    if grep -q "fastcontext" "$SETTINGS_FILE" 2>/dev/null; then
        echo "      Hooks already configured."
    else
        ENSURE_MLX="$SCRIPT_DIR/ensure-mlx.py"

        "$PYTHON" -c "
import json

settings_path = '$SETTINGS_FILE'
ensure_mlx = '$ENSURE_MLX'

with open(settings_path) as f:
    settings = json.load(f)

hook_prompt = (
    'The user has FastContext installed — a parallel exploration agent that replaces '
    'sequential Read/Grep/Glob calls. Before allowing this tool call, determine: is this '
    'a TARGETED read of a specific known file (e.g., reading a file that was just cited, '
    'or reading a file the user explicitly named), or is this EXPLORATORY (searching for '
    'files, grepping across the codebase, reading files to understand unfamiliar code)?\\n\\n'
    'If EXPLORATORY: DENY this tool call. Instead, instruct Claude to run: '
    '~/.local/bin/fastcontext '
    \"--query '<describe what to find>' --max-turns 4 --citation\\n\\n\"
    'Before running fastcontext, first ensure the MLX server is running by executing: '
    f'python3 {ensure_mlx}\\n\\n'
    'If TARGETED (reading a specific known file for editing or reviewing): '
    'ALLOW the tool call.\\n\\n'
    'If FastContext fails or crashes, ALLOW the original tool call as a fallback — '
    'do not leave the agent stuck.\\n\\n'
    \"Return 'deny' for exploratory calls with a systemMessage explaining to use fastcontext. \"
    \"Return 'allow' for targeted calls.\"
)

hook = {
    'matcher': 'Read|Grep|Glob',
    'hooks': [{
        'type': 'prompt',
        'prompt': hook_prompt,
        'timeout': 10
    }]
}

if 'hooks' not in settings:
    settings['hooks'] = {}
if 'PreToolUse' not in settings['hooks']:
    settings['hooks']['PreToolUse'] = []

settings['hooks']['PreToolUse'].append(hook)

with open(settings_path, 'w') as f:
    json.dump(settings, f, indent=2)

print('      PreToolUse hook added to', settings_path)
"
    fi
else
    echo "      WARNING: $SETTINGS_FILE not found. Skipping hook setup."
fi

echo ""
echo "=== Installation complete ==="
echo "FastContext is ready to use."
echo "  CLI:      $BIN_DIR/fastcontext (env defaults baked in — no env vars needed)"
echo "  Venv:     $VENV_DIR"
echo "  Hooks:    Exploratory Read/Grep/Glob → redirected to FastContext"
echo "  Fallback: If FastContext fails, normal tools are allowed through"
echo "  Server:   MLX server starts automatically when needed."
echo ""
echo "Restart Claude Code for hooks to take effect."
