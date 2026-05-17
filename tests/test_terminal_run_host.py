"""terminal_run_host command and host_run_service."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from mcp_terminal.commands.terminal_run_host_command import TerminalRunHostCommand
from mcp_terminal.errors import ErrorCode
from mcp_terminal.services.host_execution_config import (
    HostExecutionConfig,
    validate_host_run_request,
)


def test_validate_host_run_disabled() -> None:
    with patch(
        "mcp_terminal.services.host_execution_config.get_host_execution_config",
        return_value=HostExecutionConfig(enabled=False, allowed_commands=frozenset({"casmgr"})),
    ):
        v = validate_host_run_request("argv", None, ["casmgr", "status"])
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_EXECUTION_DISABLED


def test_validate_host_run_when_enabled() -> None:
    with patch(
        "mcp_terminal.services.host_execution_config.get_host_execution_config",
        return_value=HostExecutionConfig(enabled=True, allowed_commands=frozenset({"casmgr"})),
    ):
        assert validate_host_run_request("argv", None, ["casmgr", "status"]).ok


def test_terminal_run_host_command_returns_disabled_error() -> None:
    from pathlib import Path
    from types import SimpleNamespace

    srec = SimpleNamespace(session_dir=Path("/tmp/s"))
    resolved = SimpleNamespace(success=True, project_dir=Path("/tmp/p"), error_code=None)

    cmd = TerminalRunHostCommand()
    with (
        patch(
            "mcp_terminal.commands.terminal_run_host_command.registry_resolve_project",
            return_value=resolved,
        ),
        patch(
            "mcp_terminal.commands.terminal_run_host_command.resolve_session",
            return_value=(srec, None),
        ),
        patch(
            "mcp_terminal.commands.terminal_run_host_command.resolve_cwd",
            return_value=(".", None),
        ),
        patch(
            "mcp_terminal.commands.terminal_run_host_command.resolve_use_venv",
            return_value=False,
        ),
        patch(
            "mcp_terminal.commands.terminal_run_host_command.get_session_store",
            return_value=object(),
        ),
        patch(
            "mcp_terminal.services.host_execution_config.get_host_execution_config",
            return_value=HostExecutionConfig(enabled=False, allowed_commands=frozenset()),
        ),
    ):
        result = asyncio.run(
            cmd.execute(
                project_id="00000000-0000-4000-8000-000000000001",
                session_id="00000000-0000-4000-8000-000000000002",
                execution_kind="argv",
                argv=["true"],
            )
        )
    assert result.success is False
    assert result.error == ErrorCode.HOST_EXECUTION_DISABLED
