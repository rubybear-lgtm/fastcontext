#!/bin/bash
# Install fastcontext-mcp: create venv, install package, register MCP server, verify.
# Optionally install skill files (--install-skills).
#
# By default, tries to download a prebuilt wheel from the latest GitHub
# release (faster — no git clone). Falls back to building from git source
# if no release is available. Use --from-source to skip the prebuilt check.
set -euo pipefail

VENV_DIR="${HOME}/.cache/fastcontext/venv"
REPO_URL="git+https://github.com/rubybear-lgtm/fastcontext.git"
SKILLS_RAW_BASE="https://raw.githubusercontent.com/rubybear-lgtm/fastcontext/main/skills"

# Parse flags
TARGET="auto"
INSTALL_SKILLS=false
FROM_SOURCE=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --target) TARGET="$2"; shift 2 ;;
        --target=*) TARGET="${1#*=}"; shift ;;
        --install-skills) INSTALL_SKILLS=true; shift ;;
        --from-source) FROM_SOURCE=true; shift ;;
        --help|-h)
            cat <<'EOF'
fastcontext-mcp installer

Usage:
  install.sh [options]

Options:
  --target <tool>    Which AI coding tool(s) to register with:
                     claude | opencode | codex | both | auto (default: auto)
  --install-skills   Also download and install the FastContext skill files
                     (fastcontext, fastcontext-setup) to ~/.agents/skills/
                     and symlink them into detected tool skill directories.
  --from-source      Build from git source instead of using a prebuilt wheel.
                     Slower, but useful for development or if no release exists.
  --help, -h         Show this help message

By default, the installer downloads a prebuilt wheel from the latest
GitHub release (fast — no git clone). If no release is available, or if
--from-source is passed, it falls back to building from the git repo.

Examples:
  install.sh                                    # auto-detect tools, prebuilt wheel
  install.sh --target claude                    # Claude Code only
  install.sh --target both --install-skills     # all tools + skill files
  install.sh --from-source                      # build from git
  install.sh --install-skills                   # auto-detect + skill files
EOF
            exit 0 ;;
        *) echo "Unknown flag: $1 (use --help for usage)"; exit 1 ;;
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

INSTALL_SOURCE=""
if [ "$FROM_SOURCE" = true ]; then
    INSTALL_SOURCE="$REPO_URL"
    echo "      --from-source: building from git"
else
    # Try prebuilt wheel first; fall back to git source on failure
    WHEEL_INFO=$("$PYTHON" -c "
from fastcontext_mcp.release import resolve_wheel_url, ReleaseError
try:
    result = resolve_wheel_url(timeout=15)
    if result:
        print(result[0])
    else:
        print('NONE')
except ReleaseError:
    print('NONE')
except Exception:
    print('NONE')
" 2>/dev/null || echo "NONE")

    if [ "$WHEEL_INFO" != "NONE" ] && [ -n "$WHEEL_INFO" ]; then
        echo "      Found prebuilt wheel, downloading..."
        WHEEL_PATH=$(mktemp -t fastcontext_XXXXXX --suffix=.whl)
        if "$PYTHON" -c "
import sys
from fastcontext_mcp.release import download_wheel
try:
    download_wheel('$WHEEL_INFO', '$WHEEL_PATH', timeout=120)
    print('OK')
except Exception as e:
    print(f'FAIL: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null; then
            INSTALL_SOURCE="$WHEEL_PATH"
            echo "      Downloaded prebuilt wheel"
        else
            echo "      Wheel download failed, falling back to git source"
            rm -f "$WHEEL_PATH"
            INSTALL_SOURCE="$REPO_URL"
        fi
    else
        echo "      No prebuilt wheel available, building from git"
        INSTALL_SOURCE="$REPO_URL"
    fi
fi

uv pip install --quiet --python "$PYTHON" "fastcontext-mcp @ $INSTALL_SOURCE"
echo "      Installed into $VENV_DIR"

# Clean up downloaded wheel (uv pip install copies it into the venv)
if [[ "$INSTALL_SOURCE" == *.whl ]] && [ -f "$INSTALL_SOURCE" ]; then
    rm -f "$INSTALL_SOURCE"
fi

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
# 4. Register MCP servers (and optionally install skill files)
# -------------------------------------------------------------------
echo "[4/5] Registering MCP server(s)..."

export VENV_DIR
export REGISTER_TOOLS_STR="${REGISTER_TOOLS[*]}"
export INSTALL_SKILLS
export SKILLS_RAW_BASE

"$PYTHON" -c "
import json, os, sys
from pathlib import Path

from fastcontext_mcp.configwriter import (
    TOOL_CONFIGS, SKILL_NAMES, write_mcp_config, install_skill_file,
)

venv = os.environ['VENV_DIR']
command_path = f'{venv}/bin/fastcontext-mcp'
tools = os.environ['REGISTER_TOOLS_STR'].strip().split()
install_skills = os.environ['INSTALL_SKILLS'] == 'true'
skills_base = os.environ['SKILLS_RAW_BASE']

for tool_name in tools:
    if tool_name not in TOOL_CONFIGS:
        print(f'      Unknown tool: {tool_name}, skipping.')
        continue
    written = write_mcp_config(tool_name, command_path)
    cfg = TOOL_CONFIGS[tool_name]
    action = 'Added to' if written else 'already registered:'
    print(f'      {action} ~/{cfg[\"path\"]}')

if install_skills:
    print('      Installing skill files...')
    import urllib.request
    for skill_name in SKILL_NAMES:
        url = f'{skills_base}/{skill_name}/SKILL.md'
        try:
            content = urllib.request.urlopen(url, timeout=30).read().decode('utf-8')
        except Exception as e:
            print(f'      Failed to fetch {skill_name}: {e}')
            continue
        path = install_skill_file(skill_name, content)
        print(f'      Skill {skill_name} -> {path}')
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
if [ "$INSTALL_SKILLS" = true ]; then
    echo "  Skills: Installed to ~/.agents/skills/ (fastcontext, fastcontext-setup)"
fi
echo ""
echo "Restart your AI coding tool to activate the MCP server."
