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
REPAIR_CONFIG=false
FROM_SOURCE=false
ACTION="install"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --target) [ $# -ge 2 ] || { echo "--target requires a value"; exit 1; }; TARGET="$2"; shift 2 ;;
        --target=*) TARGET="${1#*=}"; shift ;;
        --install-skills) INSTALL_SKILLS=true; shift ;;
        --repair-config) REPAIR_CONFIG=true; shift ;;
        --from-source) FROM_SOURCE=true; shift ;;
        --update) ACTION="update"; shift ;;
        --uninstall) ACTION="uninstall"; shift ;;
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
  --repair-config    Repair FastContext launch fields, preserving other entry options.
  --update           Re-install the package and refresh already installed skills.
  --uninstall        Remove the venv, MCP config entries, and skill files.
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
  install.sh --update                           # update to latest version
  install.sh --uninstall                        # remove everything
EOF
            exit 0 ;;
        *) echo "Unknown flag: $1 (use --help for usage)"; exit 1 ;;
    esac
done

case "$TARGET" in
    claude|opencode|codex|both|auto) ;;
    *) echo "Unknown --target: $TARGET"; exit 1 ;;
esac

# -------------------------------------------------------------------
# Uninstall: remove venv, MCP config entries, and skill files
# -------------------------------------------------------------------
if [ "$ACTION" = "uninstall" ]; then
    echo "=== fastcontext-mcp uninstaller ==="
    PYTHON="$VENV_DIR/bin/python"

    # Remove MCP config entries (needs the package still installed)
    if [ -x "$PYTHON" ] && "$PYTHON" -c "import fastcontext_mcp.configwriter" 2>/dev/null; then
        echo "[1/3] Removing MCP config entries..."
        "$PYTHON" -c "
from fastcontext_mcp.configwriter import TOOL_CONFIGS, remove_mcp_config, uninstall_skill_files

for tool in TOOL_CONFIGS:
    removed = remove_mcp_config(tool)
    cfg = TOOL_CONFIGS[tool]
    if removed:
        print(f'      Removed fastcontext from ~/{cfg[\"path\"]}')

print('[2/3] Removing skill files...')
removed = uninstall_skill_files()
for p in removed:
    print(f'      Removed {p}')
if not removed:
    print('      No skill files found.')
"
    else
        echo "[1/3] Package not installed, skipping config cleanup."
        echo "[2/3] Skipping skill file cleanup."
    fi

    echo "[3/3] Removing venv..."
    if [ -d "$VENV_DIR" ]; then
        rm -rf "$VENV_DIR"
        echo "      Removed $VENV_DIR"
    else
        echo "      Venv not found at $VENV_DIR"
    fi

    echo ""
    echo "=== Uninstall complete ==="
    echo "Restart your AI coding tool to finish removal."
    exit 0
fi

# -------------------------------------------------------------------
# Update: reinstall package in place (config entries are preserved)
# -------------------------------------------------------------------
if [ "$ACTION" = "update" ]; then
    echo "=== fastcontext-mcp updater ==="
    echo "Re-installing package; preserving existing venv and registrations..."
    # Fall through to the normal install flow
fi

if [ "$ACTION" = "install" ] || [ "$ACTION" = "update" ]; then
    echo "=== fastcontext-mcp installer ==="
fi

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
    # Try prebuilt wheel first; fall back to git source on failure.
    # NOTE: This runs BEFORE the package is installed, so we use only
    # stdlib (no import from fastcontext_mcp) — the release module is
    # available after install for programmatic use, but the bootstrap
    # must be self-contained.
    WHEEL_URL=$("$PYTHON" -c "
import json, re, urllib.request, sys
API = 'https://api.github.com/repos/rubybear-lgtm/fastcontext/releases'
WHEEL_RE = re.compile(r'fastcontext_mcp-[\w.]+-py3-none-any\.whl$')
def get(url):
    req = urllib.request.Request(url, headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'fastcontext-mcp-installer',
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode('utf-8'))
try:
    release = get(API + '/latest')
except Exception:
    try:
        releases = get(API)
        release = releases[0] if releases else {}
    except Exception:
        release = {}
for asset in release.get('assets', []):
    if WHEEL_RE.search(asset.get('name', '')):
        url = asset.get('browser_download_url')
        if url:
            print(url)
            sys.exit(0)
print('NONE')
" 2>/dev/null || echo "NONE")

    if [ "$WHEEL_URL" != "NONE" ] && [ -n "$WHEEL_URL" ]; then
        echo "      Found prebuilt wheel, downloading..."
        # mktemp -d + filename is portable (macOS BSD mktemp doesn't
        # support --suffix). Preserve the original wheel filename from
        # the URL — uv pip install requires the version in the filename.
        WHEEL_DIR=$(mktemp -d)
        WHEEL_FILENAME=$(basename "$WHEEL_URL")
        WHEEL_PATH="$WHEEL_DIR/$WHEEL_FILENAME"
        if "$PYTHON" -c "
import sys, urllib.request
try:
    req = urllib.request.Request('$WHEEL_URL', headers={
        'User-Agent': 'fastcontext-mcp-installer',
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    with open('$WHEEL_PATH', 'wb') as f:
        f.write(data)
    print('OK')
except Exception as e:
    print(f'FAIL: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null; then
            INSTALL_SOURCE="$WHEEL_PATH"
            echo "      Downloaded prebuilt wheel"
        else
            echo "      Wheel download failed, falling back to git source"
            rm -rf "$WHEEL_DIR"
            INSTALL_SOURCE="$REPO_URL"
        fi
    else
        echo "      No prebuilt wheel available, building from git"
        INSTALL_SOURCE="$REPO_URL"
    fi
fi

INSTALL_OPTIONS=(--quiet --python "$PYTHON")
if [ "$ACTION" = "update" ]; then
    INSTALL_OPTIONS+=(--reinstall-package fastcontext-mcp)
fi
uv pip install "${INSTALL_OPTIONS[@]}" "fastcontext-mcp @ $INSTALL_SOURCE"
# An older release wheel may lack the APIs required by this installer.
if ! "$PYTHON" -c "import inspect; import fastcontext_mcp.verify; from fastcontext_mcp.configwriter import write_mcp_config; assert 'repair' in inspect.signature(write_mcp_config).parameters" 2>/dev/null; then
    echo "      Package lacks current setup diagnostics; installing current source..."
    uv pip install --quiet --python "$PYTHON" --reinstall-package fastcontext-mcp "fastcontext-mcp @ $REPO_URL"
fi
echo "      Installed into $VENV_DIR"

# Clean up downloaded wheel (uv pip install copies it into the venv)
if [[ "$INSTALL_SOURCE" == *.whl ]] && [ -f "$INSTALL_SOURCE" ]; then
    rm -rf "$(dirname "$INSTALL_SOURCE")"
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

# Verify the package installed successfully before using its modules
if ! "$PYTHON" -c "import fastcontext_mcp.configwriter" 2>/dev/null; then
    echo "      ERROR: fastcontext-mcp package not installed correctly."
    echo "      The uv pip install in step 2 may have failed. Re-run the installer."
    exit 1
fi

export VENV_DIR
export REGISTER_TOOLS_STR="${REGISTER_TOOLS[*]}"
export INSTALL_SKILLS
export REPAIR_CONFIG
export ACTION
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
    written = write_mcp_config(tool_name, command_path, repair=os.environ['REPAIR_CONFIG'] == 'true')
    cfg = TOOL_CONFIGS[tool_name]
    action = 'Added to' if written else 'already registered:'
    print(f'      {action} ~/{cfg[\"path\"]}')

skill_names = list(SKILL_NAMES) if install_skills else [
    name for name in SKILL_NAMES
    if os.environ['ACTION'] == 'update'
    and (Path.home() / '.agents' / 'skills' / name / 'SKILL.md').is_file()
]
if skill_names:
    print('      Installing or refreshing skill files...')
    import urllib.request
    for skill_name in skill_names:
        url = f'{skills_base}/{skill_name}/SKILL.md'
        try:
            content = urllib.request.urlopen(url, timeout=30).read().decode('utf-8')
        except Exception as e:
            raise RuntimeError(f'Failed to fetch skill {skill_name}: {e}') from e
        path = install_skill_file(skill_name, content)
        print(f'      Skill {skill_name} -> {path}')
"

# -------------------------------------------------------------------
# 5. Verify
# -------------------------------------------------------------------
echo "[5/5] Verifying..."
for tool in "${REGISTER_TOOLS[@]}"; do
    "$PYTHON" -m fastcontext_mcp.verify --tool "$tool"
done
echo "      Model inference was not tested. Use verify --connect or --inference separately."

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
