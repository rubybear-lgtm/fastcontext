import asyncio
import json
import sys
from pathlib import Path

import pytest
import tomli_w

from fastcontext_mcp import verify
from fastcontext_mcp.configwriter import TOOL_CONFIGS, write_mcp_config


@pytest.mark.parametrize("tool", TOOL_CONFIGS)
def test_registration_and_explicit_repair_preserve_custom_options(tmp_path, tool):
    path = tmp_path / TOOL_CONFIGS[tool]["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"command": ["/missing"] if tool == "opencode" else "/missing", "env": {"KEEP": "yes"}, "cwd": str(tmp_path)}
    if tool == "opencode":
        entry.update(type="local", enabled=True)
    config = {TOOL_CONFIGS[tool]["container_key"]: {"fastcontext": entry, "other": {"command": "/other"}}}
    path.write_text(tomli_w.dumps(config) if tool == "codex" else json.dumps(config))
    assert not write_mcp_config(tool, sys.executable, home=tmp_path)
    with pytest.raises(ValueError, match="missing or not executable"):
        verify.read_registration(tool, home=tmp_path)
    assert write_mcp_config(tool, sys.executable, home=tmp_path, repair=True)
    command, _, repaired = verify.read_registration(tool, home=tmp_path)
    assert command == sys.executable
    assert repaired["env"] == {"KEEP": "yes"}
    assert repaired["cwd"] == str(tmp_path)
    parsed = __import__('tomllib').loads(path.read_text()) if tool == "codex" else json.loads(path.read_text())
    assert parsed[TOOL_CONFIGS[tool]["container_key"]]["other"] == {"command": "/other"}
    assert not write_mcp_config(tool, sys.executable, home=tmp_path, repair=True)


def test_text_match_does_not_count_as_registration(tmp_path):
    (tmp_path / '.mcp.json').write_text('{"notes":"fastcontext"}')
    with pytest.raises(ValueError, match="No FastContext MCP entry"):
        verify.read_registration('claude', home=tmp_path)


@pytest.mark.parametrize("entry", [
    {"command": "~/bin/fastcontext"},
    {"command": sys.executable, "args": "not-an-array"},
    {"command": sys.executable, "enabled": False},
])
def test_invalid_launch_configuration_is_rejected(tmp_path, entry):
    (tmp_path / '.mcp.json').write_text(json.dumps({"mcpServers": {"fastcontext": entry}}))
    with pytest.raises(ValueError):
        verify.read_registration('claude', home=tmp_path)


def test_cli_reports_registration_failure(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    assert verify.main(['--tool', 'claude']) == 1
    assert 'Verification failed' in capsys.readouterr().err


def test_inference_requires_explicit_existing_repository():
    with pytest.raises(SystemExit) as error:
        verify.main(['--tool', 'claude', '--inference'])
    assert error.value.code == 2


def test_connection_check_rejects_wrong_server(tmp_path):
    # Real MCP handshake against a lightweight fixture, no model or GPU required.
    script = tmp_path / 'server.py'
    script.write_text('from mcp.server.fastmcp import FastMCP\nmcp=FastMCP("other")\nmcp.run()\n')
    with pytest.raises(ExceptionGroup) as error:
        asyncio.run(verify.check_connection(sys.executable, [str(script)], {}))
    assert 'does not expose fastcontext_explore' in str(error.value.exceptions)
