"""Tests for scripts/install.sh — syntax, flags, and help output.

These are non-destructive tests that don't run the full install (which
requires network access and a real venv). They verify the script's
structure, argument parsing, and help text.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install.sh"


@pytest.fixture
def script_path() -> Path:
    assert INSTALL_SCRIPT.exists(), "install.sh not found"
    return INSTALL_SCRIPT


# --- Shell syntax --------------------------------------------------------

class TestShellSyntax:
    def test_script_exists(self, script_path: Path):
        assert script_path.is_file()

    def test_script_is_executable(self, script_path: Path):
        assert os.access(script_path, os.X_OK), "install.sh should be executable"

    def test_bash_syntax_valid(self, script_path: Path):
        result = subprocess.run(
            ["bash", "-n", str(script_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error:\n{result.stderr}"

    def test_has_shebang(self, script_path: Path):
        first_line = script_path.read_text().splitlines()[0]
        assert first_line.startswith("#!/bin/bash") or first_line.startswith("#!/usr/bin/env bash")

    def test_has_set_strict_mode(self, script_path: Path):
        content = script_path.read_text()
        assert "set -euo pipefail" in content, "Missing strict mode (set -euo pipefail)"


# --- Help flag -----------------------------------------------------------

class TestHelpFlag:
    def test_help_exits_zero(self, script_path: Path):
        result = subprocess.run(
            ["bash", str(script_path), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def test_help_short_flag(self, script_path: Path):
        result = subprocess.run(
            ["bash", str(script_path), "-h"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def test_help_lists_options(self, script_path: Path):
        result = subprocess.run(
            ["bash", str(script_path), "--help"],
            capture_output=True, text=True,
        )
        for option in ["--target", "--install-skills", "--from-source", "--help"]:
            assert option in result.stdout, f"Missing option in help: {option}"

    def test_help_lists_tools(self, script_path: Path):
        result = subprocess.run(
            ["bash", str(script_path), "--help"],
            capture_output=True, text=True,
        )
        for tool in ["claude", "opencode", "codex", "both", "auto"]:
            assert tool in result.stdout, f"Missing tool in help: {tool}"


# --- Argument parsing ----------------------------------------------------

class TestArgumentParsing:
    def test_unknown_flag_exits_nonzero(self, script_path: Path):
        result = subprocess.run(
            ["bash", str(script_path), "--bogus"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "Unknown flag" in result.stderr or "Unknown flag" in result.stdout

    def test_target_flag_accepted(self, script_path: Path):
        """--target should be parsed before any installation begins.

        We can't run the full script, but we can verify the flag is accepted
        by checking that the script doesn't reject it with 'Unknown flag'.
        We use a timeout since the script will try to install things.
        """
        try:
            result = subprocess.run(
                ["bash", str(script_path), "--target", "claude"],
                capture_output=True, text=True, timeout=2,
            )
            # It will either start installing (timeout) or proceed
            assert "Unknown flag" not in result.stderr
        except subprocess.TimeoutExpired:
            # Script started running — flag was accepted
            pass

    def test_install_skills_flag_accepted(self, script_path: Path):
        try:
            result = subprocess.run(
                ["bash", str(script_path), "--install-skills"],
                capture_output=True, text=True, timeout=2,
            )
            assert "Unknown flag" not in result.stderr
        except subprocess.TimeoutExpired:
            pass

    def test_from_source_flag_accepted(self, script_path: Path):
        try:
            result = subprocess.run(
                ["bash", str(script_path), "--from-source"],
                capture_output=True, text=True, timeout=2,
            )
            assert "Unknown flag" not in result.stderr
        except subprocess.TimeoutExpired:
            pass

    def test_target_equals_form(self, script_path: Path):
        try:
            result = subprocess.run(
                ["bash", str(script_path), "--target=opencode"],
                capture_output=True, text=True, timeout=2,
            )
            assert "Unknown flag" not in result.stderr
        except subprocess.TimeoutExpired:
            pass


# --- Script content checks -----------------------------------------------

class TestScriptContent:
    def test_uses_configwriter_module(self, script_path: Path):
        content = script_path.read_text()
        assert "fastcontext_mcp.configwriter" in content

    def test_has_install_skills_logic(self, script_path: Path):
        content = script_path.read_text()
        assert "INSTALL_SKILLS" in content
        assert "--install-skills" in content

    def test_has_from_source_flag(self, script_path: Path):
        content = script_path.read_text()
        assert "--from-source" in content
        assert "FROM_SOURCE" in content

    def test_uses_release_module_for_wheel(self, script_path: Path):
        content = script_path.read_text()
        # The bootstrap wheel resolution is inlined using stdlib only
        # (no import from fastcontext_mcp) so it works on first install.
        # The release module is used for programmatic use after install.
        assert "api.github.com/repos/rubybear-lgtm/fastcontext/releases" in content
        assert "fastcontext_mcp" in content  # wheel name pattern
        assert "WHEEL_RE" in content or "py3-none-any" in content

    def test_has_prebuilt_fallback_to_git(self, script_path: Path):
        content = script_path.read_text()
        assert "REPO_URL" in content
        assert "falling back to git" in content or "building from git" in content

    def test_wheel_resolution_is_stdlib_only(self, script_path: Path):
        """The bootstrap must not import from fastcontext_mcp (not installed yet)."""
        content = script_path.read_text()
        # Find the wheel resolution Python block
        assert "import json, re, urllib.request, sys" in content
        # Must NOT import fastcontext_mcp.release in the bootstrap phase
        # (it's fine to use it after install in step 4)
        bootstrap_section = content.split("uv pip install")[0]
        assert "from fastcontext_mcp.release" not in bootstrap_section

    def test_uses_portable_mktemp(self, script_path: Path):
        """mktemp must not use --suffix (not supported on macOS BSD mktemp)."""
        content = script_path.read_text()
        assert "mktemp --suffix" not in content
        assert "mktemp -d" in content

    def test_has_all_five_steps(self, script_path: Path):
        content = script_path.read_text()
        for step in ["[1/5]", "[2/5]", "[3/5]", "[4/5]", "[5/5]"]:
            assert step in content, f"Missing step label: {step}"

    def test_detects_all_three_tools(self, script_path: Path):
        content = script_path.read_text()
        for func in ["has_claude", "has_opencode", "has_codex"]:
            assert func in content, f"Missing detection function: {func}"

    def test_has_verification_step(self, script_path: Path):
        content = script_path.read_text()
        assert "fastcontext_mcp.server" in content
        assert "MCP server loads OK" in content

    def test_has_done_summary(self, script_path: Path):
        content = script_path.read_text()
        assert "=== Done ===" in content
        assert "Restart your AI coding tool" in content


# --- README consistency --------------------------------------------------

class TestReadmeConsistency:
    @pytest.fixture
    def readme_content(self) -> str:
        return (REPO_ROOT / "README.md").read_text()

    def test_has_architecture_section(self, readme_content: str):
        assert "## Architecture" in readme_content or "# Architecture" in readme_content

    def test_has_install_section(self, readme_content: str):
        assert "## Install" in readme_content or "# Install" in readme_content

    def test_mentions_npx_add_skill(self, readme_content: str):
        assert "npx skills add" in readme_content

    def test_mentions_curl_install(self, readme_content: str):
        assert "curl" in readme_content
        assert "install.sh" in readme_content

    def test_mentions_all_three_tools(self, readme_content: str):
        for tool in ["Claude", "OpenCode", "Codex"]:
            assert tool in readme_content, f"Missing tool: {tool}"

    def test_has_config_file_paths(self, readme_content: str):
        assert ".mcp.json" in readme_content
        assert "opencode.json" in readme_content
        assert "config.toml" in readme_content

    def test_has_requirements_section(self, readme_content: str):
        assert "## Requirements" in readme_content or "Requirements" in readme_content
        assert "Apple Silicon" in readme_content

    def test_has_two_part_explanation(self, readme_content: str):
        assert "two-part" in readme_content.lower() or "MCP server" in readme_content
