"""MCP config and skill file installation utilities.

Used by ``scripts/install.sh``. Extracted into a module so the logic is
testable without running the full install script (which requires network
access and a real venv).

All functions accept an optional ``home`` parameter (defaulting to
``Path.home()``) so tests can point at a temporary directory.
"""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Literal, Optional

try:
    import tomli_w
except ImportError:
    tomli_w = None

ToolName = Literal["claude", "opencode", "codex"]

TOOL_CONFIGS: dict[str, dict] = {
    "claude": {
        "path": ".mcp.json",
        "format": "json",
        "container_key": "mcpServers",
        "entry_name": "fastcontext",
    },
    "opencode": {
        "path": ".config/opencode/opencode.json",
        "format": "json",
        "container_key": "mcp",
        "entry_name": "fastcontext",
    },
    "codex": {
        "path": ".codex/config.toml",
        "format": "toml",
        "container_key": "mcp_servers",
        "entry_name": "fastcontext",
    },
}

SKILL_NAMES = ("fastcontext", "fastcontext-setup")

_SKILL_LINK_DIRS: dict[str, str] = {
    "claude": ".claude/skills",
    "opencode": ".config/opencode/skills",
    # Note: Codex CLI does not have a skill directory system — it loads
    # skills from the MCP server's instructions, so no symlink is needed.
}


def _config_path(tool: str, home: Path) -> Path:
    cfg = TOOL_CONFIGS[tool]
    return home / cfg["path"]


def _mcp_entry(tool: str, command_path: str) -> dict:
    if tool == "opencode":
        return {"type": "local", "command": [command_path], "enabled": True}
    return {"command": command_path, "args": []}


def write_mcp_config(
    tool: ToolName,
    command_path: str,
    *,
    home: Optional[Path] = None,
) -> bool:
    """Write the MCP server entry into ``tool``'s config file.

    Returns True if a new entry was written, False if already present.
    Raises ValueError if ``tool`` is unknown or tomli_w is missing for TOML.
    """
    if tool not in TOOL_CONFIGS:
        raise ValueError(f"Unknown tool: {tool!r}")

    home = home or Path.home()
    cfg = TOOL_CONFIGS[tool]
    path = _config_path(tool, home)
    entry_name = cfg["entry_name"]
    container_key = cfg["container_key"]
    entry = _mcp_entry(tool, command_path)

    if cfg["format"] == "json":
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            content = path.read_text().strip()
            config = json.loads(content) if content else {}
        else:
            config = {}
        config.setdefault(container_key, {})
        if entry_name in config[container_key]:
            return False
        config[container_key][entry_name] = entry
        path.write_text(json.dumps(config, indent=2) + "\n")
        return True

    if cfg["format"] == "toml":
        if tomli_w is None:
            raise ValueError("tomli_w is required to write TOML config for codex")
        if path.exists():
            config = tomllib.loads(path.read_text())
        else:
            config = {}
        config.setdefault(container_key, {})
        if entry_name in config[container_key]:
            return False
        config[container_key][entry_name] = entry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomli_w.dumps(config))
        return True

    raise ValueError(f"Unknown format: {cfg['format']!r}")


def detect_installed_tools(*, home: Optional[Path] = None) -> list[str]:
    """Return the list of agent tools that appear to be installed.

    Detection is based on the presence of their config directories/files
    under ``home``. This mirrors the ``has_*`` shell functions in
    ``install.sh``.
    """
    home = home or Path.home()
    found: list[str] = []
    if (home / ".claude").is_dir():
        found.append("claude")
    if (home / ".config" / "opencode").is_dir():
        found.append("opencode")
    if (home / ".codex").is_dir():
        found.append("codex")
    return found


def install_skill_file(
    skill_name: str,
    content: str,
    *,
    home: Optional[Path] = None,
    symlink: bool = True,
) -> Path:
    """Write a skill's SKILL.md to the shared skills directory.

    Places the file at ``~/.agents/skills/<skill_name>/SKILL.md`` and, when
    ``symlink`` is True, creates relative symlinks from each detected agent
    tool's skills directory (Claude, OpenCode) to the shared location.

    Returns the path to the written file.
    Raises ValueError if ``skill_name`` is not a known FastContext skill.
    """
    if skill_name not in SKILL_NAMES:
        raise ValueError(
            f"Unknown skill: {skill_name!r} (expected one of {SKILL_NAMES})"
        )

    home = home or Path.home()
    target_dir = home / ".agents" / "skills" / skill_name
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "SKILL.md"
    target_file.write_text(content)

    if symlink:
        for tool, rel_path in _SKILL_LINK_DIRS.items():
            link_dir = home / rel_path
            if not link_dir.exists():
                continue
            link = link_dir / skill_name
            rel = os.path.relpath(target_dir, link_dir)
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(rel)

    return target_file
