#!/usr/bin/env python3
"""Ensure the MLX LM server is running. Start it as a daemon if not.

The server persists across Claude Code sessions — multiple sessions share
the same instance. Logs are written to ~/.cache/fastcontext/mlx-server.log.
"""

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

MODEL = os.environ.get("MODEL", "mattrobenolt/FastContext-1.0-4B-SFT-mlx-bf16")
PORT = int(os.environ.get("PORT", "8080"))
VENV_PYTHON = Path.home() / ".cache" / "fastcontext" / "venv" / "bin" / "python"
LOG_DIR = Path.home() / ".cache" / "fastcontext"
LOG_FILE = LOG_DIR / "mlx-server.log"
TIMEOUT = 120


def is_server_ready(port: int) -> bool:
    try:
        url = f"http://localhost:{port}/v1/models"
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_server(model: str, port: int) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    with open(LOG_FILE, "a") as log:
        subprocess.Popen(
            [python, "-m", "mlx_lm.server", "--model", model, "--port", str(port)],
            stdout=log,
            stderr=log,
            start_new_session=True,
        )


def main() -> None:
    if is_server_ready(PORT):
        print(f"MLX server already running on port {PORT}.")
        return

    print(f"Starting MLX server with model {MODEL} on port {PORT}...")
    start_server(MODEL, PORT)

    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        if is_server_ready(PORT):
            print(f"MLX server ready on port {PORT}.")
            return
        time.sleep(2)

    print(f"WARNING: MLX server did not respond within {TIMEOUT}s.", file=sys.stderr)
    print(f"Check logs: {LOG_FILE}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
