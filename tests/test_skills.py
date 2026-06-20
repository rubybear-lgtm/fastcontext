"""Tests for SKILL.md content — frontmatter, required sections, and link consistency.

Validates that the skill files are well-formed and contain the sections
needed for agent-driven onboarding.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).parent.parent / "skills"
SETUP_SKILL = SKILLS_DIR / "fastcontext-setup" / "SKILL.md"
USAGE_SKILL = SKILLS_DIR / "fastcontext" / "SKILL.md"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse YAML frontmatter (simple key: value parsing)."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    return fm


@pytest.fixture
def setup_content() -> str:
    return SETUP_SKILL.read_text()


@pytest.fixture
def usage_content() -> str:
    return USAGE_SKILL.read_text()


# --- Frontmatter ---------------------------------------------------------

class TestFrontmatter:
    def test_setup_has_frontmatter(self, setup_content: str):
        fm = parse_frontmatter(setup_content)
        assert fm.get("name") == "fastcontext-setup"
        assert "description" in fm
        assert len(fm["description"]) > 20

    def test_usage_has_frontmatter(self, usage_content: str):
        fm = parse_frontmatter(usage_content)
        assert fm.get("name") == "fastcontext"
        assert "description" in fm
        assert len(fm["description"]) > 20

    def test_setup_description_mentions_install_triggers(self, setup_content: str):
        fm = parse_frontmatter(setup_content)
        desc = fm["description"].lower()
        assert "install" in desc or "setup" in desc or "configure" in desc

    def test_usage_description_mentions_explore_triggers(self, usage_content: str):
        fm = parse_frontmatter(usage_content)
        desc = fm["description"].lower()
        assert "explore" in desc or "codebase" in desc or "search" in desc


# --- Setup skill: agent-driven procedure ---------------------------------

class TestSetupSkillAgentDriven:
    def test_has_architecture_section(self, setup_content: str):
        assert "Architecture" in setup_content

    def test_has_prerequisites(self, setup_content: str):
        assert "Prerequisites" in setup_content
        assert "Apple Silicon" in setup_content

    def test_has_installation_procedure(self, setup_content: str):
        assert "Installation procedure" in setup_content
        assert "agent-executed" in setup_content.lower()

    def test_instructs_agent_to_execute(self, setup_content: str):
        """The skill must tell the AGENT to run commands, not the user."""
        assert "You (the AI agent)" in setup_content or "agent-executed" in setup_content

    def test_has_guard_check_step(self, setup_content: str):
        assert "Guard check" in setup_content
        assert "uname" in setup_content

    def test_has_already_installed_check(self, setup_content: str):
        assert "already installed" in setup_content.lower() or "NOT_INSTALLED" in setup_content

    def test_has_permission_step(self, setup_content: str):
        assert "permission" in setup_content.lower() or "Shall I proceed" in setup_content

    def test_has_install_script_command(self, setup_content: str):
        assert "install.sh" in setup_content
        assert "curl" in setup_content

    def test_has_verify_step(self, setup_content: str):
        assert "Verify" in setup_content
        assert "fastcontext_mcp.server" in setup_content

    def test_has_restart_instruction(self, setup_content: str):
        assert "restart" in setup_content.lower()
        assert "AI coding tool" in setup_content

    def test_has_manual_fallback(self, setup_content: str):
        assert "Manual installation" in setup_content
        assert "uv venv" in setup_content

    def test_has_troubleshooting(self, setup_content: str):
        assert "Troubleshooting" in setup_content

    def test_mentions_all_three_tools(self, setup_content: str):
        for tool in ["Claude Code", "OpenCode", "Codex CLI"]:
            assert tool in setup_content, f"Missing tool: {tool}"

    def test_has_target_flag_options(self, setup_content: str):
        for target in ["--target claude", "--target opencode", "--target codex"]:
            assert target in setup_content, f"Missing target option: {target}"


# --- Usage skill: architecture docs --------------------------------------

class TestUsageSkillDocs:
    def test_has_how_it_works_section(self, usage_content: str):
        assert "How it works" in usage_content

    def test_explains_two_part_system(self, usage_content: str):
        assert "two-part" in usage_content or "two-part system" in usage_content

    def test_mentions_mcp_server_role(self, usage_content: str):
        assert "MCP server" in usage_content

    def test_mentions_skill_role(self, usage_content: str):
        assert "skill" in usage_content.lower()

    def test_has_prerequisite_section(self, usage_content: str):
        assert "Prerequisite" in usage_content

    def test_has_usage_section(self, usage_content: str):
        assert "Usage" in usage_content or "fastcontext_explore" in usage_content

    def test_has_query_examples(self, usage_content: str):
        assert "Query Examples" in usage_content or "query" in usage_content.lower()

    def test_has_max_turns_guidance(self, usage_content: str):
        assert "max_turns" in usage_content

    def test_has_when_to_use(self, usage_content: str):
        assert "When to use" in usage_content

    def test_has_when_not_to_use(self, usage_content: str):
        assert "When NOT to use" in usage_content


# --- Link consistency ----------------------------------------------------

class TestLinkConsistency:
    def test_install_url_matches_repo(self, setup_content: str):
        assert "rubybear-lgtm/fastcontext" in setup_content
        assert "raw.githubusercontent.com" in setup_content

    def test_venv_path_is_consistent(self, setup_content: str):
        assert "~/.cache/fastcontext/venv" in setup_content
        assert "fastcontext-mcp" in setup_content

    def test_config_paths_are_correct(self, setup_content: str):
        assert "~/.mcp.json" in setup_content
        assert "~/.config/opencode/opencode.json" in setup_content
        assert "~/.codex/config.toml" in setup_content


# --- File structure ------------------------------------------------------

class TestSkillFileStructure:
    def test_setup_skill_file_exists(self):
        assert SETUP_SKILL.exists()

    def test_usage_skill_file_exists(self):
        assert USAGE_SKILL.exists()

    def test_setup_skill_dir_name_matches_frontmatter(self, setup_content: str):
        fm = parse_frontmatter(setup_content)
        assert SETUP_SKILL.parent.name == fm["name"]

    def test_usage_skill_dir_name_matches_frontmatter(self, usage_content: str):
        fm = parse_frontmatter(usage_content)
        assert USAGE_SKILL.parent.name == fm["name"]
