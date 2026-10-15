"""Validate real skill metadata and examples against the exposed tool schema."""

import ast
import asyncio
import re
from pathlib import Path

import pytest
import yaml

from fastcontext_mcp.server import mcp

SKILLS = Path(__file__).resolve().parents[1] / "skills"


@pytest.mark.parametrize("directory", sorted(SKILLS.iterdir()), ids=lambda p: p.name)
def test_skill_metadata_and_local_links(directory):
    content = (directory / "SKILL.md").read_text()
    frontmatter = re.match(r"^---\n(.*?)\n---\n", content, re.S)
    assert frontmatter
    metadata = yaml.safe_load(frontmatter[1])
    assert metadata["name"] == directory.name
    assert isinstance(metadata["description"], str)
    assert 0 < len(metadata["description"]) <= 1024
    for link in re.findall(r"\]\(([^)]+)\)", content):
        if "://" not in link and not link.startswith("#"):
            assert (directory / link.split("#")[0]).exists(), link


def test_usage_call_examples_match_live_tool_schema():
    schema = asyncio.run(mcp.list_tools())[0].inputSchema
    content = (SKILLS / "fastcontext" / "SKILL.md").read_text()
    calls = re.findall(r"```text\n(fastcontext_explore\(.*?)\n```", content, re.S)
    assert calls
    for example in calls:
        call = ast.parse(example).body[0].value
        arguments = {arg.arg: ast.literal_eval(arg.value) for arg in call.keywords}
        assert set(arguments) <= set(schema["properties"])
        assert set(schema["required"]) <= set(arguments)
        assert Path(arguments["work_dir"]).is_absolute()
        assert 1 <= arguments["max_turns"] <= 10
