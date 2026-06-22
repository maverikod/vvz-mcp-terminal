"""Host-side terminal execution path."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from mcp_terminal.errors import ErrorCode
from mcp_terminal.services.host_execution_config import HostCommandValidation, HostExecutionConfig
from mcp_terminal.services.host_session_executor import HostRunResult, HostSessionExecutor
from mcp_terminal.services.host_run_identity import HostRunIdentity
from mcp_terminal.services.shell_state import write_shell_state, ShellState

_CFG = HostExecutionConfig(enabled=True, allowed_commands=frozenset({"true", "cd"}))
_IDENTITY = HostRunIdentity(
    run_as_mode="project_owner",
    sudo_user="1000",
    sudo_group="1000",
    effective_uid=1000,
    effective_gid=1000,
    primary_basename="true",
)


def test_host_session_executor_runs_and_updates_cwd(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "sub").mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    write_shell_state(session_dir, ShellState(cwd=".", use_venv=False))

    mock_proc = MagicMock()
    mock_proc.wait.return_value = None
    mock_proc.returncode = 0

    with (
        patch(
            "mcp_terminal.services.host_session_executor.get_host_execution_config",
            return_value=_CFG,
        ),
        patch(
            "mcp_terminal.services.host_session_executor.validate_host_run_request",
            return_value=HostCommandValidation(ok=True, segments=("cd sub",)),
        ),
        patch(
            "mcp_terminal.services.host_session_executor.sudo_nopasswd_available",
            return_value=True,
        ),
        patch(
            "mcp_terminal.services.host_session_executor.resolve_host_identity",
            return_value=_IDENTITY,
        ),
        patch(
            "mcp_terminal.services.host_session_executor.subprocess.Popen",
            return_value=mock_proc,
        ) as popen,
        patch(
            "mcp_terminal.services.running_terminal_jobs.register",
            return_value=None,
        ),
        patch(
            "mcp_terminal.services.running_terminal_jobs.unregister",
            return_value=None,
        ),
    ):
        executor = HostSessionExecutor()
        result = executor.run(
            project_id="00000000-0000-4000-8000-000000000001",
            session_id="00000000-0000-4000-8000-000000000002",
            seq=1,
            session_dir=session_dir,
            project_dir=project_dir,
            timeout_seconds=30,
            effective_cwd=".",
            execution_kind="shell",
            command="cd sub",
            argv=None,
            use_venv=False,
        )
    assert isinstance(result, HostRunResult)
    assert result.status == "completed"
    assert result.exit_code == 0
    launch_argv = popen.call_args[0][0]
    assert launch_argv[0:3] == ["/usr/bin/sudo", "-n", "-u"]


def test_host_session_executor_root_mode_runs_without_sudo(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    write_shell_state(session_dir, ShellState(cwd=".", use_venv=False))

    root_cfg = HostExecutionConfig(
        enabled=True,
        allowed_commands=frozenset({"true"}),
        run_as_default="root",
    )
    root_identity = HostRunIdentity(
        run_as_mode="root",
        sudo_user="root",
        sudo_group=None,
        effective_uid=0,
        effective_gid=0,
        primary_basename="true",
    )

    mock_proc = MagicMock()
    mock_proc.wait.return_value = None
    mock_proc.returncode = 0

    with (
        patch(
            "mcp_terminal.services.host_session_executor.get_host_execution_config",
            return_value=root_cfg,
        ),
        patch(
            "mcp_terminal.services.host_session_executor.validate_host_run_request",
            return_value=HostCommandValidation(ok=True, segments=("true",)),
        ),
        patch(
            "mcp_terminal.services.host_session_executor.sudo_nopasswd_available",
            return_value=False,
        ) as mock_sudo,
        patch(
            "mcp_terminal.services.host_session_executor.resolve_host_identity",
            return_value=root_identity,
        ),
        patch(
            "mcp_terminal.services.host_session_executor.subprocess.Popen",
            return_value=mock_proc,
        ) as popen,
        patch(
            "mcp_terminal.services.running_terminal_jobs.register",
            return_value=None,
        ),
        patch(
            "mcp_terminal.services.running_terminal_jobs.unregister",
            return_value=None,
        ),
    ):
        executor = HostSessionExecutor()
        result = executor.run(
            project_id="00000000-0000-4000-8000-000000000001",
            session_id="00000000-0000-4000-8000-000000000002",
            seq=1,
            session_dir=session_dir,
            project_dir=project_dir,
            timeout_seconds=30,
            effective_cwd=".",
            execution_kind="shell",
            command="true",
            argv=None,
            use_venv=False,
        )
    assert result.status == "completed"
    mock_sudo.assert_not_called()
    launch_argv = popen.call_args[0][0]
    assert launch_argv[0] == "/bin/bash"


def test_host_session_executor_rejects_when_validation_fails(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()

    with (
        patch(
            "mcp_terminal.services.host_session_executor.get_host_execution_config",
            return_value=_CFG,
        ),
        patch(
            "mcp_terminal.services.host_session_executor.validate_host_run_request",
            return_value=HostCommandValidation(
                ok=False,
                error_code="HOST_FORBIDDEN_COMMAND",
                detail="docker forbidden",
            ),
        ),
    ):
        executor = HostSessionExecutor()
        result = executor.run(
            project_id="00000000-0000-4000-8000-000000000001",
            session_id="00000000-0000-4000-8000-000000000002",
            seq=1,
            session_dir=session_dir,
            project_dir=project_dir,
            timeout_seconds=30,
            effective_cwd=".",
            execution_kind="shell",
            command="true",
            argv=None,
            use_venv=False,
        )
    assert result.status == "failed"
    assert result.exit_code is None


def test_host_session_executor_rejects_when_sudo_missing(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()

    with (
        patch(
            "mcp_terminal.services.host_session_executor.get_host_execution_config",
            return_value=_CFG,
        ),
        patch(
            "mcp_terminal.services.host_session_executor.validate_host_run_request",
            return_value=HostCommandValidation(ok=True),
        ),
        patch(
            "mcp_terminal.services.host_session_executor.sudo_nopasswd_available",
            return_value=False,
        ),
    ):
        executor = HostSessionExecutor()
        result = executor.run(
            project_id="00000000-0000-4000-8000-000000000001",
            session_id="00000000-0000-4000-8000-000000000002",
            seq=1,
            session_dir=session_dir,
            project_dir=project_dir,
            timeout_seconds=30,
            effective_cwd=".",
            execution_kind="shell",
            command="true",
            argv=None,
            use_venv=False,
        )
    assert result.error_code == ErrorCode.HOST_SUDO_NOT_CONFIGURED


def test_host_job_writes_execution_target(tmp_path: Path) -> None:
    from mcp_terminal.jobs.terminal_host_execution_job import (
        HostJobParams,
        TerminalHostExecutionJob,
    )

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()

    mock_result = HostRunResult(
        exit_code=0,
        timed_out=False,
        status="completed",
        identity=_IDENTITY,
    )

    mock_exec = MagicMock()
    mock_exec.run.return_value = mock_result
    job = TerminalHostExecutionJob(
        HostJobParams(
            project_id="00000000-0000-4000-8000-000000000001",
            session_id="00000000-0000-4000-8000-000000000002",
            seq=1,
            session_dir=session_dir,
            project_dir=project_dir,
            timeout_seconds=30,
            execution_kind="shell",
            command="true",
            use_venv=False,
        )
    )
    job._executor = mock_exec
    job.run()
    meta = json.loads((session_dir / "000001.meta.json").read_text(encoding="utf-8"))
    assert meta["execution_target"] == "host"
    assert meta["run_as_mode"] == "project_owner"
    assert meta["effective_uid"] == 1000
