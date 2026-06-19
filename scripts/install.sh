#!/bin/bash
# Install FastContext and all dependencies, download the MLX model, and verify.
# Uses uv for virtual environment management.
set -euo pipefail

MODEL="${MODEL:-mattrobenolt/FastContext-1.0-4B-SFT-mlx-bf16}"
VENV_DIR="${HOME}/.cache/fastcontext/venv"
BIN_DIR="${HOME}/.local/bin"

echo "=== FastContext Installer ==="

# -------------------------------------------------------------------
# 1. Check for uv
# -------------------------------------------------------------------
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
echo "[1/6] uv $(uv --version | awk '{print $2}') OK"

# -------------------------------------------------------------------
# 2. Create virtual environment with Python 3.12+
# -------------------------------------------------------------------
echo "[2/6] Setting up virtual environment at $VENV_DIR..."
uv venv "$VENV_DIR" --python ">=3.12" --quiet
PYTHON="$VENV_DIR/bin/python"
echo "      Python $($PYTHON --version | awk '{print $2}') in venv"

# -------------------------------------------------------------------
# 3. Install packages
# -------------------------------------------------------------------
echo "[3/6] Installing packages..."
uv pip install --quiet --python "$PYTHON" mlx-lm
uv pip install --quiet --python "$PYTHON" "git+https://github.com/microsoft/fastcontext.git"
echo "      Packages installed."

# -------------------------------------------------------------------
# 4. Verify imports
# -------------------------------------------------------------------
echo "[4/6] Verifying imports..."
"$PYTHON" -c "
from fastcontext.agent.agent_factory import make_fastcontext_agent
import mlx_lm
print('      All imports OK.')
"

# -------------------------------------------------------------------
# 5. Symlink fastcontext CLI to PATH
# -------------------------------------------------------------------
echo "[5/6] Linking CLI..."
mkdir -p "$BIN_DIR"
ln -sf "$VENV_DIR/bin/fastcontext" "$BIN_DIR/fastcontext"
echo "      fastcontext -> $BIN_DIR/fastcontext"

# -------------------------------------------------------------------
# 6. Download model
# -------------------------------------------------------------------
echo "[6/6] Downloading model: $MODEL (this may take a few minutes on first run)..."
"$PYTHON" -c "
from huggingface_hub import snapshot_download
path = snapshot_download('$MODEL')
print(f'      Model cached at: {path}')
"

echo ""
echo "=== Installation complete ==="
echo "FastContext is ready to use."
echo "  CLI:  $BIN_DIR/fastcontext"
echo "  Venv: $VENV_DIR"
echo "  MLX server will start automatically when needed."
