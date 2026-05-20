"""terminal_run_host command and host_run_service."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mcp_terminal.commands.terminal_run_host_command import TerminalRunHostCommand
from mcp_terminal.errors import ErrorCode
from mcp_terminal.services.host_execution_config import (
    HostCommandValidation,
    HostExecutionConfig,
    validate_host_run_request,
)
from mcp_terminal.services.host_run_service import enqueue_host_terminal_run


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


def test_enqueue_host_reject_writes_audit(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    srec = SimpleNamespace(session_dir=session_dir)
    session_store = SimpleNamespace(touch_activity=lambda *_a, **_k: None)

    async def _run() -> None:
        with patch(
            "mcp_terminal.services.host_run_service.validate_host_run_request",
            return_value=HostCommandValidation(
                ok=False,
                error_code=ErrorCode.HOST_COMMAND_NOT_ALLOWED,
            ),
        ):
            result = await enqueue_host_terminal_run(
                project_id="p",
                session_id="s",
                srec=srec,
                execution_kind="argv",
                cmd_str=None,
                argv_list=["rm", "-rf", "/"],
                effective_cwd=".",
                timeout_seconds=30,
                use_venv=False,
                project_dir=project_dir,
                session_store=session_store,
            )
        assert result.success is False
        audit_path = session_dir / "audit.jsonl"
        assert audit_path.is_file()
        line = audit_path.read_text(encoding="utf-8").strip().splitlines()[-1]
        record = json.loads(line)
        assert record["execution_target"] == "host"
        assert record["policy_code"] == ErrorCode.HOST_COMMAND_NOT_ALLOWED
        assert record["policy_decision"] == "rejected"
        assert record["resolved_cwd_on_host"] == "."

    asyncio.run(_run())
