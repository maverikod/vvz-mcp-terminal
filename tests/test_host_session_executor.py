"""Host-side terminal execution path."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_terminal.services.host_execution_config import HostCommandValidation, HostExecutionConfig
from mcp_terminal.services.host_session_executor import HostSessionExecutor
from mcp_terminal.services.shell_state import read_shell_state, write_shell_state, ShellState

_CFG = HostExecutionConfig(enabled=True, allowed_commands=frozenset({"true", "cd"}))


def test_host_session_executor_runs_and_updates_cwd(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "sub").mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    write_shell_state(session_dir, ShellState(cwd=".", use_venv=False))

    with (
        patch(
            "mcp_terminal.services.host_session_executor.get_host_execution_config",
            return_value=_CFG,
        ),
        patch(
            "mcp_terminal.services.host_session_executor.validate_host_run_request",
            return_value=HostCommandValidation(ok=True),
        ),
    ):
        executor = HostSessionExecutor()
        exit_code, timed_out, status = executor.run(
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
    assert status == "completed"
    assert exit_code == 0
    assert read_shell_state(session_dir).cwd == "sub"


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
        exit_code, timed_out, status = executor.run(
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
    assert status == "failed"
    assert exit_code is None


def test_host_job_writes_execution_target(tmp_path: Path) -> None:
    from mcp_terminal.jobs.terminal_host_execution_job import HostJobParams, TerminalHostExecutionJob

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
    ):
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
        job.run()
    meta = json.loads((session_dir / "000001.meta.json").read_text(encoding="utf-8"))
    assert meta["execution_target"] == "host"
