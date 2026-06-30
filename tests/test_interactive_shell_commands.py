"""Unit tests for sandbox-only interactive shell commands."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mcp_terminal.commands.terminal_attach_command import TerminalAttachCommand
from mcp_terminal.commands.terminal_detach_command import TerminalDetachCommand
from mcp_terminal.commands.terminal_read_shell_command import TerminalReadShellCommand
from mcp_terminal.commands.terminal_resize_command import TerminalResizeCommand
from mcp_terminal.commands.terminal_send_command import TerminalSendCommand
from mcp_terminal.services.interactive_shell import InteractiveShell


def test_attach_rejects_without_kept_container(tmp_path: Path) -> None:
    record = SimpleNamespace(
        project_id="00000000-0000-4000-8000-000000000001",
        session_id="00000000-0000-4000-8000-000000000002",
        session_dir=tmp_path,
    )
    with (
        patch(
            "mcp_terminal.commands.terminal_attach_command.resolve_session",
            return_value=(record, None),
        ),
        patch(
            "mcp_terminal.commands.terminal_attach_command.get_session_store",
            return_value=SimpleNamespace(touch_activity=lambda *_a, **_k: None),
        ),
        patch(
            "mcp_terminal.commands.terminal_attach_command.attach_shell",
            return_value=(None, "CONTAINER_NOT_RUNNING"),
        ),
    ):
        result = asyncio.run(
            TerminalAttachCommand().execute(
                project_id=record.project_id,
                session_id=record.session_id,
            )
        )
    assert result.success is False
    assert result.error == "CONTAINER_NOT_RUNNING"


def test_attach_returns_shell_status(tmp_path: Path) -> None:
    record = SimpleNamespace(
        project_id="00000000-0000-4000-8000-000000000001",
        session_id="00000000-0000-4000-8000-000000000002",
        session_dir=tmp_path,
    )
    proc = SimpleNamespace(poll=lambda: None)
    shell = InteractiveShell(
        project_id=record.project_id,
        session_id=record.session_id,
        shell_id=f"{record.project_id}:{record.session_id}",
        container_name="mcp-term-test",
        master_fd=-1,
        proc=proc,
    )
    with (
        patch(
            "mcp_terminal.commands.terminal_attach_command.resolve_session",
            return_value=(record, None),
        ),
        patch(
            "mcp_terminal.commands.terminal_attach_command.get_session_store",
            return_value=SimpleNamespace(touch_activity=lambda *_a, **_k: None),
        ),
        patch(
            "mcp_terminal.commands.terminal_attach_command.attach_shell", return_value=(shell, None)
        ),
    ):
        result = asyncio.run(
            TerminalAttachCommand().execute(
                project_id=record.project_id,
                session_id=record.session_id,
                command="python",
            )
        )
    assert result.success is True
    assert result.data["shell_id"] == shell.shell_id
    assert result.data["running"] is True


def test_interactive_command_wrappers_delegate_to_service() -> None:
    with patch("mcp_terminal.commands.terminal_send_command.send_shell", return_value=None):
        sent = asyncio.run(TerminalSendCommand().execute(shell_id="s", data="pwd\n"))
    assert sent.success is True
    assert sent.data["bytes_written"] == 4

    with patch(
        "mcp_terminal.commands.terminal_read_shell_command.read_shell",
        return_value=({"data": "ok", "next_offset": 2}, None),
    ):
        read = asyncio.run(TerminalReadShellCommand().execute(shell_id="s", offset=0))
    assert read.success is True
    assert read.data["data"] == "ok"

    with patch("mcp_terminal.commands.terminal_resize_command.resize_shell", return_value=None):
        resized = asyncio.run(TerminalResizeCommand().execute(shell_id="s", cols=80, rows=24))
    assert resized.success is True
    assert resized.data["cols"] == 80

    with patch("mcp_terminal.commands.terminal_detach_command.close_shell", return_value=None):
        detached = asyncio.run(TerminalDetachCommand().execute(shell_id="s"))
    assert detached.success is True
    assert detached.data["detached"] is True
