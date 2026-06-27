"""terminal_host_exec command and host_run_service."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mcp_terminal.commands.terminal_host_exec_command import TerminalHostExecCommand
from mcp_terminal.errors import ErrorCode
from mcp_terminal.services.host_execution_config import (
    HostCommandValidation,
    HostExecutionConfig,
    HostSshConfig,
    validate_host_run_request,
)
from mcp_terminal.services.host_run_service import enqueue_host_ssh_terminal_run


def _ssh_cfg(
    *,
    enabled: bool = True,
    allowed: frozenset[str] = frozenset({"casmgr"}),
    secrets_path: str = "/tmp/mcp-terminal-test-secrets",
) -> HostExecutionConfig:
    return HostExecutionConfig(
        enabled=enabled,
        allowed_commands=allowed,
        secrets_path=secrets_path,
        ssh=HostSshConfig(
            host="127.0.0.1",
            port=22,
            target_users=("mcp-terminal-host",),
            known_hosts_path="/etc/mcp-terminal/ssh_known_hosts",
            connect_timeout=10,
            key_manager_script="/usr/lib/mcp-terminal/manage-session-keys.sh",
        ),
    )


def test_validate_host_run_disabled() -> None:
    with patch(
        "mcp_terminal.services.host_execution_config.get_host_execution_config",
        return_value=_ssh_cfg(enabled=False),
    ):
        v = validate_host_run_request("argv", None, ["casmgr", "status"])
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_EXECUTION_DISABLED


def test_validate_host_run_when_enabled(tmp_path: Path) -> None:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir(mode=0o700)
    with patch(
        "mcp_terminal.services.host_execution_config.get_host_execution_config",
        return_value=_ssh_cfg(secrets_path=str(secrets_dir)),
    ):
        assert validate_host_run_request("argv", None, ["casmgr", "status"]).ok


def test_terminal_host_exec_schema_has_target_user() -> None:
    from mcp_terminal.commands.terminal_host_exec_schema import get_terminal_host_exec_schema

    schema = get_terminal_host_exec_schema()
    assert "target_user" in schema["properties"]
    assert "project_id" not in schema["required"]
    assert "session_id" not in schema["required"]
    assert schema["additionalProperties"] is False


def test_terminal_host_exec_metadata_required_fields() -> None:
    meta = TerminalHostExecCommand.metadata()
    for key in (
        "detailed_description",
        "parameters",
        "return_value",
        "usage_examples",
        "error_cases",
        "best_practices",
    ):
        assert key in meta
    assert "host_ssh" in meta["return_value"]["success"]["data"]["execution_target"]


def test_terminal_host_exec_command_returns_disabled_error() -> None:
    srec = SimpleNamespace(session_dir=Path("/tmp/s"))
    resolved = SimpleNamespace(success=True, project_dir=Path("/tmp/p"), error_code=None)

    cmd = TerminalHostExecCommand()
    with (
        patch(
            "mcp_terminal.commands.terminal_host_exec_command.registry_resolve_project",
            return_value=resolved,
        ),
        patch(
            "mcp_terminal.commands.terminal_host_exec_command.resolve_session",
            return_value=(srec, None),
        ),
        patch(
            "mcp_terminal.commands.terminal_host_exec_command.resolve_cwd",
            return_value=(".", None),
        ),
        patch(
            "mcp_terminal.commands.terminal_host_exec_command.resolve_use_venv",
            return_value=False,
        ),
        patch(
            "mcp_terminal.commands.terminal_host_exec_command.get_session_store",
            return_value=object(),
        ),
        patch(
            "mcp_terminal.services.host_execution_config.get_host_execution_config",
            return_value=_ssh_cfg(enabled=False, allowed=frozenset()),
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


def test_terminal_host_exec_sessionless_enqueues_without_session_lookup() -> None:
    cmd = TerminalHostExecCommand()

    async def _fake_enqueue(**kwargs):
        assert kwargs["srec"] is None
        assert kwargs["project_dir"] is None
        assert kwargs["session_store"] is None
        assert kwargs["effective_cwd"] == "/root"
        return type("R", (), {"success": True, "data": {"host_run_id": "host-x"}})()

    with (
        patch(
            "mcp_terminal.commands.terminal_host_exec_command.resolve_session",
            side_effect=AssertionError("session lookup must not run"),
        ),
        patch(
            "mcp_terminal.commands.terminal_host_exec_command.registry_resolve_project",
            side_effect=AssertionError("project lookup must not run"),
        ),
        patch(
            "mcp_terminal.commands.terminal_host_exec_command.enqueue_host_ssh_terminal_run",
            side_effect=_fake_enqueue,
        ),
    ):
        result = asyncio.run(
            cmd.execute(
                execution_kind="argv",
                argv=["hostname"],
            )
        )

    assert result.success is True


def test_enqueue_host_ssh_reject_writes_audit(tmp_path: Path) -> None:
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
            result = await enqueue_host_ssh_terminal_run(
                project_id="p",
                session_id="s",
                srec=srec,
                execution_kind="argv",
                cmd_str=None,
                argv_list=["rm", "-rf", "/"],
                effective_cwd=".",
                timeout_seconds=30,
                use_venv=False,
                target_user=None,
                project_dir=project_dir,
                session_store=session_store,
            )
        assert result.success is False
        audit_path = session_dir / "audit.jsonl"
        assert audit_path.is_file()
        line = audit_path.read_text(encoding="utf-8").strip().splitlines()[-1]
        record = json.loads(line)
        assert record["execution_target"] == "host_ssh"
        assert record["policy_code"] == ErrorCode.HOST_COMMAND_NOT_ALLOWED
        assert record["policy_decision"] == "rejected"

    asyncio.run(_run())
