# FastContext

An [agent skill](https://github.com/vercel-labs/skills) that integrates [Microsoft FastContext](https://github.com/microsoft/fastcontext) for efficient parallel codebase exploration.

FastContext is a specialized exploration agent that runs Read, Glob, and Grep operations in parallel using a fine-tuned 4B model running locally on Apple Silicon via MLX. It returns compact file-line citations, reducing main-agent token consumption by up to 60%.

## Install

```bash
npx skills add rubybear-lgtm/fastcontext
```

## Prerequisites

- Python 3.12+
- macOS with Apple Silicon (M1/M2/M3/M4)

## What happens on first use

1. The skill detects FastContext is not installed and runs the setup script
2. The setup script installs `fastcontext` and `mlx-lm` via pip
3. It downloads the `mattrobenolt/FastContext-1.0-4B-SFT-mlx-bf16` model (~2.5 GB)
4. It runs a smoke test to verify everything works
5. On subsequent uses, the MLX server starts automatically if not already running

No manual server management needed. The MLX server persists across sessions and is shared by all concurrent agent sessions.

## Usage

Once installed, your agent will use FastContext automatically when broad codebase exploration is needed. You can also trigger it explicitly:

> "Use FastContext to explore the authentication system"

The agent runs:
```bash
fastcontext --query "Find authentication middleware, session handling, and token validation" --max-turns 4 --citation
```

## License

MIT
