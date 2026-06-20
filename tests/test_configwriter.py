"""Tests for fastcontext_mcp.configwriter — MCP config and skill file installation.

These tests run against a temporary HOME directory so they don't touch the
user's real config files.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from fastcontext_mcp.configwriter import (
    SKILL_NAMES,
    TOOL_CONFIGS,
    detect_installed_tools,
    install_skill_file,
    write_mcp_config,
)


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point Path.home() and HOME env at a temporary directory."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


# --- write_mcp_config ----------------------------------------------------

class TestWriteMcpConfigClaude:
    def test_creates_new_config(self, fake_home: Path):
        result = write_mcp_config("claude", "/fake/venv/bin/fastcontext-mcp")
        assert result is True

        config_path = fake_home / ".mcp.json"
        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert "mcpServers" in config
        assert "fastcontext" in config["mcpServers"]
        entry = config["mcpServers"]["fastcontext"]
        assert entry["command"] == "/fake/venv/bin/fastcontext-mcp"
        assert entry["args"] == []

    def test_idempotent(self, fake_home: Path):
        cmd = "/fake/venv/bin/fastcontext-mcp"
        assert write_mcp_config("claude", cmd) is True
        assert write_mcp_config("claude", cmd) is False

        config_path = fake_home / ".mcp.json"
        config = json.loads(config_path.read_text())
        assert len(config["mcpServers"]) == 1

    def test_preserves_existing_entries(self, fake_home: Path):
        config_path = fake_home / ".mcp.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({
            "mcpServers": {
                "other-tool": {"command": "/bin/other", "args": []}
            }
        }))

        write_mcp_config("claude", "/fake/venv/bin/fastcontext-mcp")

        config = json.loads(config_path.read_text())
        assert "other-tool" in config["mcpServers"]
        assert "fastcontext" in config["mcpServers"]


class TestWriteMcpConfigOpenCode:
    def test_creates_new_config(self, fake_home: Path):
        result = write_mcp_config("opencode", "/fake/venv/bin/fastcontext-mcp")
        assert result is True

        config_path = fake_home / ".config" / "opencode" / "opencode.json"
        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert "mcp" in config
        assert "fastcontext" in config["mcp"]
        entry = config["mcp"]["fastcontext"]
        assert entry["type"] == "local"
        assert entry["command"] == ["/fake/venv/bin/fastcontext-mcp"]
        assert entry["enabled"] is True

    def test_idempotent(self, fake_home: Path):
        cmd = "/fake/venv/bin/fastcontext-mcp"
        assert write_mcp_config("opencode", cmd) is True
        assert write_mcp_config("opencode", cmd) is False


class TestWriteMcpConfigCodex:
    def test_creates_new_config(self, fake_home: Path):
        result = write_mcp_config("codex", "/fake/venv/bin/fastcontext-mcp")
        assert result is True

        config_path = fake_home / ".codex" / "config.toml"
        assert config_path.exists()
        config = tomllib.loads(config_path.read_text())
        assert "mcp_servers" in config
        assert "fastcontext" in config["mcp_servers"]
        entry = config["mcp_servers"]["fastcontext"]
        assert entry["command"] == "/fake/venv/bin/fastcontext-mcp"
        assert entry["args"] == []

    def test_idempotent(self, fake_home: Path):
        cmd = "/fake/venv/bin/fastcontext-mcp"
        assert write_mcp_config("codex", cmd) is True
        assert write_mcp_config("codex", cmd) is False

    def test_preserves_existing_entries(self, fake_home: Path):
        config_path = fake_home / ".codex" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('[mcp_servers.other]\ncommand = "/bin/other"\nargs = []\n')

        write_mcp_config("codex", "/fake/venv/bin/fastcontext-mcp")

        config = tomllib.loads(config_path.read_text())
        assert "other" in config["mcp_servers"]
        assert "fastcontext" in config["mcp_servers"]


class TestWriteMcpConfigErrors:
    def test_unknown_tool_raises(self, fake_home: Path):
        with pytest.raises(ValueError, match="Unknown tool"):
            write_mcp_config("unknown", "/fake/path")

    def test_all_tools_in_configs(self):
        assert set(TOOL_CONFIGS.keys()) == {"claude", "opencode", "codex"}


# --- detect_installed_tools ----------------------------------------------

class TestDetectInstalledTools:
    def test_empty_home(self, fake_home: Path):
        assert detect_installed_tools() == []

    def test_detects_claude(self, fake_home: Path):
        (fake_home / ".claude").mkdir()
        assert detect_installed_tools() == ["claude"]

    def test_detects_opencode(self, fake_home: Path):
        (fake_home / ".config" / "opencode").mkdir(parents=True)
        assert detect_installed_tools() == ["opencode"]

    def test_detects_codex(self, fake_home: Path):
        (fake_home / ".codex").mkdir()
        assert detect_installed_tools() == ["codex"]

    def test_detects_all(self, fake_home: Path):
        (fake_home / ".claude").mkdir()
        (fake_home / ".config" / "opencode").mkdir(parents=True)
        (fake_home / ".codex").mkdir()
        assert detect_installed_tools() == ["claude", "opencode", "codex"]

    def test_order_is_consistent(self, fake_home: Path):
        (fake_home / ".codex").mkdir()
        (fake_home / ".claude").mkdir()
        (fake_home / ".config" / "opencode").mkdir(parents=True)
        assert detect_installed_tools() == ["claude", "opencode", "codex"]


# --- install_skill_file --------------------------------------------------

class TestInstallSkillFile:
    def test_writes_skill_file(self, fake_home: Path):
        content = "---\nname: test\n---\n# Test\n"
        path = install_skill_file("fastcontext", content, symlink=False)
        assert path == fake_home / ".agents" / "skills" / "fastcontext" / "SKILL.md"
        assert path.read_text() == content

    def test_creates_symlinks_for_claude(self, fake_home: Path):
        (fake_home / ".claude" / "skills").mkdir(parents=True)
        content = "# Test\n"
        install_skill_file("fastcontext", content)

        link = fake_home / ".claude" / "skills" / "fastcontext"
        assert link.is_symlink()
        assert link.resolve() == (fake_home / ".agents" / "skills" / "fastcontext").resolve()

    def test_creates_symlinks_for_opencode(self, fake_home: Path):
        (fake_home / ".config" / "opencode" / "skills").mkdir(parents=True)
        content = "# Test\n"
        install_skill_file("fastcontext-setup", content)

        link = fake_home / ".config" / "opencode" / "skills" / "fastcontext-setup"
        assert link.is_symlink()
        assert link.resolve() == (fake_home / ".agents" / "skills" / "fastcontext-setup").resolve()

    def test_no_symlink_when_tool_absent(self, fake_home: Path):
        content = "# Test\n"
        install_skill_file("fastcontext", content)

        assert not (fake_home / ".claude" / "skills").exists()
        assert not (fake_home / ".config" / "opencode" / "skills").exists()

    def test_overwrites_existing_symlink(self, fake_home: Path):
        (fake_home / ".claude" / "skills").mkdir(parents=True)
        link = fake_home / ".claude" / "skills" / "fastcontext"
        link.symlink_to("/some/old/target")

        install_skill_file("fastcontext", "# New\n")

        assert link.is_symlink()
        assert link.resolve() == (fake_home / ".agents" / "skills" / "fastcontext").resolve()

    def test_unknown_skill_raises(self, fake_home: Path):
        with pytest.raises(ValueError, match="Unknown skill"):
            install_skill_file("unknown-skill", "# content", symlink=False)

    def test_skill_names_are_canonical(self):
        assert SKILL_NAMES == ("fastcontext", "fastcontext-setup")
