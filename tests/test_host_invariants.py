"""Host execution invariants H-1..H-11 (SSH model, tech_spec §28.7)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from mcp_terminal.config.host_execution_schema import HOST_EXECUTION_EMPTY_ALLOWLIST_LOG
from mcp_terminal.errors import ErrorCode
from mcp_terminal.commands.terminal_host_exec_command import TerminalHostExecCommand
from mcp_terminal.services.host_execution_config import (
    HostCommandValidation,
    HostExecutionConfig,
    HostSshConfig,
    validate_host_argv_command,
    validate_host_run_request,
    validate_host_shell_command,
    validate_key_access_guard,
    warn_if_host_execution_enabled_without_commands,
)
from mcp_terminal.services.host_run_service import enqueue_host_ssh_terminal_run
from mcp_terminal.services.shell_state import (
    ShellState,
    normalize_cwd,
    read_shell_state,
    resolve_cwd,
    write_shell_state,
)

_SSH = HostSshConfig(
    host="127.0.0.1",
    port=22,
    target_users=("hostuser",),
    known_hosts_path="/etc/mcp-terminal/ssh_known_hosts",
    connect_timeout=10,
    key_manager_script="/usr/lib/mcp-terminal/manage-session-keys.sh",
)

_HE_CFG = HostExecutionConfig(
    enabled=True,
    allowed_commands=frozenset({"pytest", "git", "true", "sleep"}),
    ssh=_SSH,
)


def _patch_host_config(cfg: HostExecutionConfig):
    return patch(
        "mcp_terminal.services.host_execution_config.get_host_execution_config",
        return_value=cfg,
    )


def test_h1_disabled_gate_rejects_without_queueing_job(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    srec = SimpleNamespace(session_dir=session_dir)
    session_store = SimpleNamespace(touch_activity=lambda *_a, **_k: None)

    async def _run() -> None:
        with (
            _patch_host_config(
                HostExecutionConfig(enabled=False, allowed_commands=frozenset({"true"})),
            ),
            patch("mcp_terminal.services.host_run_service.enqueue_coroutine") as mock_enqueue,
        ):
            result = await enqueue_host_ssh_terminal_run(
                project_id="p",
                session_id="s",
                srec=srec,
                execution_kind="argv",
                cmd_str=None,
                argv_list=["true"],
                effective_cwd=".",
                timeout_seconds=30,
                use_venv=False,
                target_user=None,
                project_dir=project_dir,
                session_store=session_store,
            )
        assert result.success is False
        assert result.error == ErrorCode.HOST_EXECUTION_DISABLED
        mock_enqueue.assert_not_called()

    asyncio.run(_run())


def test_h2_empty_allowlist_rejects_request() -> None:
    with _patch_host_config(
        HostExecutionConfig(enabled=True, allowed_commands=frozenset(), ssh=_SSH),
    ):
        v = validate_host_run_request("argv", None, ["true"])
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_EXECUTION_DISABLED


def test_h2_empty_allowlist_startup_warning(caplog: pytest.LogCaptureFixture) -> None:
    cfg = {"terminal": {"host_execution": {"enabled": True, "allowed_commands": []}}}
    with caplog.at_level(logging.WARNING):
        warn_if_host_execution_enabled_without_commands(cfg)
    assert HOST_EXECUTION_EMPTY_ALLOWLIST_LOG in caplog.text


def test_h5_docker_still_forbidden() -> None:
    allowed = frozenset({"docker", "pytest"})
    v = validate_host_shell_command("/usr/bin/docker ps", allowed)
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_FORBIDDEN_COMMAND


def test_h12_key_guard_rejects_key_reference(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    key_dir = session_dir / ".ssh"
    key_dir.mkdir()
    private = key_dir / "session_ed25519"
    private.write_text("x", encoding="utf-8")
    v = validate_key_access_guard("argv", None, ["cat", str(private)], session_dir)
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_KEY_ACCESS_FORBIDDEN


@pytest.mark.parametrize("bad_cwd", ["/absolute/path", "../escape", "foo/../../outside"])
def test_h6_resolve_cwd_rejects_absolute_and_dotdot(tmp_path: Path, bad_cwd: str) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    cwd, err = resolve_cwd(session_dir, bad_cwd)
    assert cwd is None
    assert err == "INVALID_CWD"


def test_h6_terminal_host_exec_rejects_invalid_cwd_before_enqueue(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    srec = SimpleNamespace(session_dir=session_dir)
    resolved = SimpleNamespace(success=True, project_dir=project_dir, error_code=None)

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
            "mcp_terminal.commands.terminal_host_exec_command.get_session_store",
            return_value=object(),
        ),
        patch("mcp_terminal.services.host_run_service.enqueue_coroutine") as mock_enqueue,
    ):
        result = asyncio.run(
            cmd.execute(
                project_id="00000000-0000-4000-8000-000000000001",
                session_id="00000000-0000-4000-8000-000000000002",
                execution_kind="argv",
                argv=["true"],
                cwd="/abs/cwd",
            )
        )

    assert result.success is False
    assert result.error == ErrorCode.INVALID_CWD
    mock_enqueue.assert_not_called()


def test_h8_validation_failure_preserves_shell_state(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    write_shell_state(session_dir, ShellState(cwd="keep-me", use_venv=False))
    before = (session_dir / "shell_state.json").read_text(encoding="utf-8")

    with _patch_host_config(_HE_CFG):
        v = validate_host_run_request(
            "shell",
            "docker ps",
            None,
            session_dir=session_dir,
        )
    assert not v.ok
    after = (session_dir / "shell_state.json").read_text(encoding="utf-8")
    assert after == before
    assert read_shell_state(session_dir).cwd == "keep-me"


def test_h3_hard_forbidden_sudo_argv() -> None:
    allowed = frozenset({"sudo", "pytest"})
    v = validate_host_argv_command(["sudo", "apt", "update"], allowed)
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_FORBIDDEN_COMMAND
