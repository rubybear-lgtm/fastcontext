---
name: fastcontext-setup
description: Install, update, diagnose, repair registration, or uninstall the FastContext MCP server and its skills on Apple Silicon Macs. Use when the user requests FastContext setup or a connection needs troubleshooting.
---

# FastContext Setup

FastContext has two parts: a lightweight MCP server exposing `fastcontext_explore`, and skill instructions that guide its use. The server starts a disposable MLX model worker only during exploration. Model weights are released after each request; a machine-wide lock serializes inference.

## Select the operation

Act on the user's requested tool and scope. An explicit install, update, repair, or uninstall request authorizes that operation; do not require a duplicate confirmation. Ask only when a necessary choice or broader side effect is not covered by the request. Diagnosing a missing tool does not authorize installing it.

Target options are `claude`, `opencode`, `codex`, `both` (all three), and `auto`. Prefer the explicitly requested target. `auto` detects tools and falls back to Claude if none are found, so inspect the target before using it. Config paths used by this installer are `~/.mcp.json`, `~/.config/opencode/opencode.json`, and `~/.codex/config.toml`; existing custom registrations may live elsewhere.

Run commands yourself when authorized. Do not ask the user to paste commands that you can execute. Use the checked-out installer when working on a local branch; the remote installer below runs `main`, which may not contain local changes.

## Install

1. Check `uname -s` and `uname -m`. Inference requires macOS with Apple Silicon (`Darwin`, `arm64`), GPU access, ripgrep (`rg`) on the MCP process’s `PATH`, and roughly 5 GB available RAM. The first exploration may download the model; import verification alone does not download or test it.
2. Check `"$HOME/.cache/fastcontext/venv/bin/fastcontext-mcp"` exists and is executable. If installed, diagnose registration and connection rather than reinstalling by default.
3. Install for the requested target. Replace `codex` below as appropriate:

```bash
curl -fsSL https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/scripts/install.sh -o /tmp/fastcontext-install.sh
bash /tmp/fastcontext-install.sh --target codex --install-skills
```

The installer creates `~/.cache/fastcontext/venv`, installs `uv` if needed, registers the MCP server, and installs both skills to `~/.agents/skills/`. It prefers the latest release wheel and falls back to git source if no wheel is available or the wheel lacks the installer’s diagnostic APIs. To install current source explicitly, add `--from-source`; “latest release” does not mean the latest commit on `main`.

If installation fails, report the failing stage and error. Do not claim completion or repeatedly reinstall without diagnosing the failure.

## Verify in stages

Use the venv's Python and the requested target:

```bash
"$HOME/.cache/fastcontext/venv/bin/python" -m fastcontext_mcp.verify --tool codex
"$HOME/.cache/fastcontext/venv/bin/python" -m fastcontext_mcp.verify --tool codex --connect
```

The first command parses the actual MCP entry, checks its executable, and imports the lightweight server. The second launches the configured command and tests the MCP handshake and tool discovery. Neither proves model loading or inference works.

To test inference when setup verification requires it, use an existing absolute project path:

```bash
"$HOME/.cache/fastcontext/venv/bin/python" -m fastcontext_mcp.verify --tool codex --inference --work-dir /absolute/path/to/project
```

This loads the model and runs one exploration. It may download model files on first use. Inspect the returned citations against the selected project: a completed inference request is not a guarantee of answer accuracy. The temporary worker exits afterward.

Report which checks passed, what was not tested, the affected config paths, and whether installed skill files changed. Reconnect the FastContext MCP server or restart the client to load updates. A fresh diagnostic connection does not prove an existing client has reconnected.

## Diagnose or repair

- **Tool absent:** Check whether the client supports deferred tool discovery, whether FastContext is enabled/registered in its active config, and whether reconnecting surfaces it. Absence from a tool list is not proof of missing software.
- **Missing or malformed registration:** Parse the target's config; do not use a text search for `fastcontext` as proof. Preserve unrelated entries and custom settings.
- **Stale launch command:** Ordinary installation preserves existing entries. For an explicitly requested repair, run the installer with `--target codex --repair-config`. It resets managed launch fields while retaining other entry options, including environment and working-directory settings. Recheck the connection afterward.
- **Old package without the diagnostic module or `work_dir`:** Inspect the installed version/source and update through the requested channel. Do not treat an unavailable new command as proof the entire installation is broken.
- **Import succeeds but inference fails:** Check GPU access, available RAM, model download/cache errors, and worker stderr. Do not report import success as model success.
- **Source verification failure:** The engine rejects citations that were not backed by observed source lines. Check search errors and `rg` availability, refine the request using known facts, or use direct search. Do not treat an unverified answer as a successful exploration.
- **Wrong repository:** Pass `work_dir` as an absolute path on each exploration call. A shell directory change does not retarget an existing MCP connection.
- **Waiting or slow requests:** Every request reloads the model, and other clients may hold the shared inference slot. Avoid parallel retries that only add to the queue.

## Update

Use the same installer with the requested target and channel:

```bash
bash /tmp/fastcontext-install.sh --target codex --update
```

Fetch the installer first if it has not been fetched during this task. `--update` reinstalls the package in the existing venv and refreshes already installed FastContext skills. Add `--install-skills` to install both skills if they are not installed, or `--from-source` for current source. Registrations remain unchanged unless `--repair-config` is explicitly requested. This is not an atomic rollback mechanism; report any failure and verify the resulting state before retrying.

Run staged verification again and reconnect the client. Updates to files do not replace code already loaded in existing processes.

## Uninstall

The uninstall operation removes the venv, FastContext MCP entries from all three supported config paths, and shared FastContext skill files/links. Explain that scope if the user only requested removal from one client; use a targeted config removal instead when that is their intent.

```bash
bash /tmp/fastcontext-install.sh --uninstall
```

Fetch the installer first if needed. If the package is missing or broken, the script skips configuration and skill cleanup; inspect for leftover entries and report partial removal. The script does not stop already running processes or remove cached model downloads. Reconnect or close affected client connections, and do not kill unrelated Python processes.

## Manual fallback

If automation is unsuitable, use the existing local installer or install from source with `uv` and edit only the requested registration. This still needs network access unless dependencies are already cached:

```bash
uv venv "$HOME/.cache/fastcontext/venv" --python ">=3.12"
uv pip install --python "$HOME/.cache/fastcontext/venv/bin/python" "fastcontext-mcp @ git+https://github.com/rubybear-lgtm/fastcontext.git"
```

Use the fully expanded **absolute executable path** in config; do not save a literal `~`. Claude/Codex entries use `command` plus an `args` array; local OpenCode entries use `type: "local"`, a `command` array, and `enabled: true`. Prefer the package's `write_mcp_config` helper when available. Run parsed registration checks and a real connection test afterward.
