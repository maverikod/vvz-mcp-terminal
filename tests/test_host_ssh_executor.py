"""Host SSH executor unit tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from mcp_terminal.errors import ErrorCode
from mcp_terminal.services.host_execution_config import HostExecutionConfig, HostSshConfig
from mcp_terminal.services.host_ssh_executor import HostSSHExecutor, _write_remote_exec_script


def _cfg() -> HostExecutionConfig:
    return HostExecutionConfig(
        enabled=True,
        allowed_commands=frozenset({"true"}),
        ssh=HostSshConfig(
            host="127.0.0.1",
            port=22,
            target_users=("hostuser",),
            known_hosts_path="/etc/mcp-terminal/ssh_known_hosts",
            connect_timeout=5,
            key_manager_script="/usr/lib/mcp-terminal/manage-session-keys.sh",
        ),
    )


def test_host_ssh_executor_rejects_missing_session_key(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    executor = HostSSHExecutor()
    with patch(
        "mcp_terminal.services.host_ssh_executor.get_host_execution_config",
        return_value=_cfg(),
    ), patch(
        "mcp_terminal.services.host_ssh_executor.validate_host_run_request",
        return_value=type("V", (), {"ok": True, "error_code": None})(),
    ):
        result = executor.run(
            project_id="p",
            session_id="s",
            seq=1,
            session_dir=session_dir,
            project_dir=project_dir,
            timeout_seconds=5,
            effective_cwd=".",
            execution_kind="argv",
            command=None,
            argv=["true"],
        )
    assert result.status == "failed"
    assert result.error_code == ErrorCode.HOST_EXECUTION_DISABLED


def test_sessionless_host_script_accepts_absolute_cwd(tmp_path: Path) -> None:
    script = _write_remote_exec_script(
        tmp_path,
        "000001",
        project_dir=None,
        effective_cwd="/root",
        execution_kind="argv",
        command=None,
        argv=["true"],
        use_venv=False,
    )
    text = script.read_text(encoding="utf-8")
    assert "cd /root" in text


def test_host_ssh_job_writes_host_ssh_meta(tmp_path: Path) -> None:
    from mcp_terminal.jobs.terminal_host_ssh_job import HostSSHJobParams, TerminalHostSSHJob

    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (session_dir / "000001.stdout.log").touch()
    (session_dir / "000001.stderr.log").touch()
    mock_executor = MagicMock()
    mock_executor.run.return_value = type(
        "R",
        (),
        {
            "exit_code": 0,
            "timed_out": False,
            "status": "completed",
            "target_user": "hostuser",
            "error_code": None,
        },
    )()
    job = TerminalHostSSHJob(
        HostSSHJobParams(
            project_id="p",
            session_id="s",
            seq=1,
            session_dir=session_dir,
            project_dir=project_dir,
            timeout_seconds=5,
            execution_kind="argv",
            argv=["true"],
            target_user="hostuser",
        ),
        executor=mock_executor,
    )
    with patch(
        "mcp_terminal.jobs.terminal_host_ssh_job.get_host_execution_config",
        return_value=_cfg(),
    ):
        job.run()
    meta = (session_dir / "000001.meta.json").read_text(encoding="utf-8")
    assert "host_ssh" in meta
    assert "hostuser" in meta


def test_sessionless_host_ssh_job_passes_none_project_dir(tmp_path: Path) -> None:
    from mcp_terminal.jobs.terminal_host_ssh_job import HostSSHJobParams, TerminalHostSSHJob

    (tmp_path / "000001.stdout.log").touch()
    (tmp_path / "000001.stderr.log").touch()
    mock_executor = MagicMock()
    mock_executor.run.return_value = type(
        "R",
        (),
        {
            "exit_code": 0,
            "timed_out": False,
            "status": "completed",
            "target_user": "root",
            "error_code": None,
        },
    )()
    job = TerminalHostSSHJob(
        HostSSHJobParams(
            project_id="host",
            session_id="host-run",
            seq=1,
            session_dir=tmp_path,
            project_dir=None,
            timeout_seconds=5,
            execution_kind="argv",
            argv=["hostname"],
            target_user="root",
        ),
        executor=mock_executor,
    )
    with patch(
        "mcp_terminal.jobs.terminal_host_ssh_job.get_host_execution_config",
        return_value=_cfg(),
    ):
        job.run()
    assert mock_executor.run.call_args.kwargs["project_dir"] is None
