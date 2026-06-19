# FastContext Troubleshooting

## Installation Issues

### Python version too old

FastContext requires Python 3.12+. Check with:

```bash
python3 --version
```

If below 3.12, install a newer Python via Homebrew:

```bash
brew install python@3.13
```

### Import errors after installation

If `python3 -c "import fastcontext"` fails after running `install.sh`, the package may have installed into a different Python environment.

```bash
which python3
python3 -m pip show fastcontext
```

Ensure `pip install` targets the same `python3` that `which python3` returns. If using pyenv or conda, activate the correct environment first.

### `uv tool install` vs `pip install`

`uv tool install .` creates an isolated environment that exposes the CLI but does NOT make the package importable by `python3`. Always use `pip install` for FastContext so that both the CLI and Python imports work.

## MLX Server Issues

### Server not starting

Check the log file:

```bash
cat ~/.cache/fastcontext/mlx-server.log
```

Common causes:
- **Port in use**: Another process is using port 8080. Check with `lsof -i :8080`. Either kill the process or set a different port via `PORT=9090 python3 scripts/ensure-mlx.py`.
- **Insufficient memory**: The 4B model requires ~5 GB of RAM. Close memory-intensive applications.
- **Model not downloaded**: The first start downloads the model from Hugging Face (~2.5 GB). Ensure internet connectivity.

### Server started but FastContext times out

The MLX server may still be loading the model. The 4B model takes 10-30s to load on M4 Pro. Wait and retry.

Check if the server is responding:

```bash
curl http://localhost:8080/v1/models
```

### Stopping the MLX server

The server runs as a background daemon and persists across sessions. To stop it:

```bash
pkill -f "mlx_lm.server"
```

### Changing the model

To use a different model:

```bash
pkill -f "mlx_lm.server"
export MODEL="your-model-name"
python3 scripts/ensure-mlx.py
```

## FastContext CLI Issues

### "No final answer after N turns"

The model ran out of turns before finding relevant code. Increase `--max-turns`:

```bash
fastcontext -q "your query" --max-turns 8 --citation
```

### Empty or unhelpful results

Refine the query to be more specific:
- Bad: "Find the code" — too vague
- Good: "Find the authentication middleware that validates JWT tokens and the session store implementation"

### Slow responses

The 4B model runs locally on the GPU. Response time depends on:
- Model size (4B is the smallest/fastest option)
- Number of turns (each turn is an LLM call + tool execution)
- Repository size (more files = more exploration needed)

Typical latency: 5-15s for a 4-turn exploration on M4 Pro.

## Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL` | `mattrobenolt/FastContext-1.0-4B-SFT-mlx-bf16` | Model for MLX server |
| `PORT` | `8080` | Port for MLX server |
| `BASE_URL` | `http://localhost:8080/v1` | LLM endpoint for FastContext |
| `API_KEY` | `no-key-needed` | API key (local MLX needs none) |

## Using a Remote LLM Instead of MLX

To use an OpenAI-compatible API instead of local MLX:

```bash
export BASE_URL="https://api.openai.com/v1"
export MODEL="gpt-4o-mini"
export API_KEY="sk-..."
```

Skip the MLX server steps — FastContext connects directly to the remote endpoint.
