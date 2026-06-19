# fastcontext-mcp

MCP server wrapping [Microsoft FastContext](https://github.com/microsoft/fastcontext) with in-process MLX inference on Apple Silicon.

Loads the fine-tuned `mattrobenolt/FastContext-1.0-4B-SFT-mlx-bf16` model directly via `mlx_lm` — no external server, no env vars, no subprocess management.

## Install

```bash
uv pip install "fastcontext-mcp @ git+https://github.com/rubybear-lgtm/fastcontext.git"
```

## Run

```bash
fastcontext-mcp
```

## License

MIT
