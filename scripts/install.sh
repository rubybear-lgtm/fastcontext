#!/bin/bash
# Install FastContext and all dependencies, download the MLX model, and verify.
set -euo pipefail

MODEL="${MODEL:-mattrobenolt/FastContext-1.0-4B-SFT-mlx-bf16}"
PYTHON="${PYTHON:-python3}"

echo "=== FastContext Installer ==="
echo "Python: $($PYTHON --version 2>&1)"
echo ""

# -------------------------------------------------------------------
# 1. Check Python version
# -------------------------------------------------------------------
PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]; }; then
    echo "ERROR: Python 3.12+ required, found $PY_VERSION"
    exit 1
fi
echo "[1/5] Python $PY_VERSION OK"

# -------------------------------------------------------------------
# 2. Install packages
# -------------------------------------------------------------------
echo "[2/5] Installing packages..."
$PYTHON -m pip install --quiet --upgrade pip
$PYTHON -m pip install --quiet mlx-lm
$PYTHON -m pip install --quiet "git+https://github.com/microsoft/fastcontext.git"
echo "      Packages installed."

# -------------------------------------------------------------------
# 3. Verify imports
# -------------------------------------------------------------------
echo "[3/5] Verifying imports..."
$PYTHON -c "
from fastcontext.agent.agent_factory import make_fastcontext_agent
import mlx_lm
print('      All imports OK.')
"

# -------------------------------------------------------------------
# 4. Download model
# -------------------------------------------------------------------
echo "[4/5] Downloading model: $MODEL (this may take a few minutes on first run)..."
$PYTHON -c "
from huggingface_hub import snapshot_download
path = snapshot_download('$MODEL')
print(f'      Model cached at: {path}')
"

# -------------------------------------------------------------------
# 5. Smoke test — start MLX server, hit it, shut it down
# -------------------------------------------------------------------
echo "[5/5] Smoke test..."
PORT=18932  # ephemeral port for testing
$PYTHON -m mlx_lm.server --model "$MODEL" --port $PORT &
SERVER_PID=$!

cleanup() { kill $SERVER_PID 2>/dev/null || true; wait $SERVER_PID 2>/dev/null || true; }
trap cleanup EXIT

READY=false
for i in $(seq 1 60); do
    if curl -s "http://localhost:$PORT/v1/models" > /dev/null 2>&1; then
        READY=true
        break
    fi
    sleep 2
done

if [ "$READY" = true ]; then
    echo "      MLX server started and responding."
    echo ""
    echo "=== Installation complete ==="
    echo "FastContext is ready to use."
    echo "The MLX server will be started automatically when needed."
else
    echo "WARNING: MLX server did not respond within 120s."
    echo "The model may still be loading. Try running manually:"
    echo "  python3 -m mlx_lm.server --model $MODEL --port 8080"
fi
