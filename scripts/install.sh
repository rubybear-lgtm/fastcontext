#!/bin/bash
# Install FastContext and all dependencies, download the MLX model,
# configure hooks, and verify.
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
echo "[1/7] uv $(uv --version | awk '{print $2}') OK"

# -------------------------------------------------------------------
# 2. Create virtual environment with Python 3.12+
# -------------------------------------------------------------------
echo "[2/7] Setting up virtual environment at $VENV_DIR..."
uv venv "$VENV_DIR" --python ">=3.12" --quiet
PYTHON="$VENV_DIR/bin/python"
echo "      Python $($PYTHON --version | awk '{print $2}') in venv"

# -------------------------------------------------------------------
# 3. Install packages
# -------------------------------------------------------------------
echo "[3/7] Installing packages..."
uv pip install --quiet --python "$PYTHON" mlx-lm
uv pip install --quiet --python "$PYTHON" "git+https://github.com/microsoft/fastcontext.git"
echo "      Packages installed."

# -------------------------------------------------------------------
# 4. Verify imports
# -------------------------------------------------------------------
echo "[4/7] Verifying imports..."
"$PYTHON" -c "
from fastcontext.agent.agent_factory import make_fastcontext_agent
import mlx_lm
print('      All imports OK.')
"

# -------------------------------------------------------------------
# 5. Symlink fastcontext CLI to PATH
# -------------------------------------------------------------------
echo "[5/7] Linking CLI..."
mkdir -p "$BIN_DIR"
ln -sf "$VENV_DIR/bin/fastcontext" "$BIN_DIR/fastcontext"
echo "      fastcontext -> $BIN_DIR/fastcontext"

# -------------------------------------------------------------------
# 6. Download model
# -------------------------------------------------------------------
echo "[6/7] Downloading model: $MODEL (this may take a few minutes on first run)..."
"$PYTHON" -c "
from huggingface_hub import snapshot_download
path = snapshot_download('$MODEL')
print(f'      Model cached at: {path}')
"

# -------------------------------------------------------------------
# 7. Install PreToolUse hook into Claude Code settings
# -------------------------------------------------------------------
echo "[7/7] Configuring hooks..."
SETTINGS_FILE="${HOME}/.claude/settings.json"

if [ -f "$SETTINGS_FILE" ]; then
    # Check if hooks already configured
    if grep -q "fastcontext" "$SETTINGS_FILE" 2>/dev/null; then
        echo "      Hooks already configured."
    else
        # Find the ensure-mlx.py path relative to install location
        ENSURE_MLX="$SCRIPT_DIR/ensure-mlx.py"

        "$PYTHON" -c "
import json, sys

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
    'MODEL=mattrobenolt/FastContext-1.0-4B-SFT-mlx-bf16 API_KEY=no-key-needed '
    'BASE_URL=http://localhost:8080/v1 ~/.local/bin/fastcontext '
    \"--query '<describe what to find>' --max-turns 4 --citation\\n\\n\"
    'Before running fastcontext, first ensure the MLX server is running by executing: '
    f'python3 {ensure_mlx}\\n\\n'
    'If TARGETED (reading a specific known file for editing or reviewing): '
    'ALLOW the tool call.\\n\\n'
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
    echo "      You can manually configure hooks later."
fi

echo ""
echo "=== Installation complete ==="
echo "FastContext is ready to use."
echo "  CLI:    $BIN_DIR/fastcontext"
echo "  Venv:   $VENV_DIR"
echo "  Hooks:  Exploratory Read/Grep/Glob calls will be redirected to FastContext"
echo "  Server: MLX server starts automatically when needed."
echo ""
echo "Restart Claude Code for hooks to take effect."
