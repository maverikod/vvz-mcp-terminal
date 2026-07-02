"""Tests for the MCP Terminal info command and packaged guide."""

from __future__ import annotations

import asyncio
from pathlib import Path

from mcp_terminal.commands.info_command import InfoCommand
from mcp_terminal.commands.info_resources import TERMINAL_INFO_MARKDOWN
from mcp_terminal.package_info import package_version
from mcp_terminal.term_server import _TERMINAL_COMMAND_TYPES

ROOT = Path(__file__).resolve().parents[1]


def test_info_command_registered_like_ai_editor_style() -> None:
    names = [cmd_cls.name for cmd_cls in _TERMINAL_COMMAND_TYPES]
    assert "info" in names
    assert names.index("info") == 0


def test_info_command_returns_packaged_markdown() -> None:
    result = asyncio.run(InfoCommand().execute())
    assert result.success is True
    assert result.data["guide_version"] == "1.0"
    assert result.data["package"]["version"] == package_version()
    assert result.data["markdown"] == TERMINAL_INFO_MARKDOWN
    assert [cmd["name"] for cmd in result.data["registered_commands"]] == [
        cmd_cls.name for cmd_cls in _TERMINAL_COMMAND_TYPES
    ]
    assert all(cmd["version"] for cmd in result.data["registered_commands"])
    assert "terminal_host_exec" in result.data["markdown"]
    assert "read_only" in result.data["markdown"]
    assert "scratch_write" in result.data["markdown"]
    assert "WORKSPACE_WRITE_NOT_ALLOWED" in result.data["markdown"]
    assert "/usr/share/doc/mcp-terminal-docker/MCP_TERMINAL_INFO.md" in result.data["docs"]


def test_info_command_rejects_unknown_params_like_ai_editor() -> None:
    result = asyncio.run(InfoCommand().execute(unexpected="x"))
    assert result.success is False
    assert result.error == "VALIDATION_ERROR"
    assert result.data["field"] == "unexpected"


def test_debian_package_installs_same_info_markdown() -> None:
    build_script = (ROOT / "docker/build-deb.sh").read_text(encoding="utf-8")
    assert "mcp_terminal/docs/INFO.md" in build_script
    assert "MCP_TERMINAL_INFO.md" in build_script
    assert "render-info-texi.py" in build_script


def test_info_command_has_no_manual_command_catalog() -> None:
    source = (ROOT / "mcp_terminal/commands/info_command.py").read_text(encoding="utf-8")
    assert "registered_command_entries()" in source
    assert '"terminal_run"' not in source
