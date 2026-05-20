"""
MVP acceptance criteria from tech_spec §21 — unit-testable subset.

Maps sandbox MVP items that do not require live Docker. Criteria that need a
running container are implemented in ``tests/test_sandbox_docker_e2e.py`` (see
pointers below). ``terminal_run`` queue E2E: ``test_terminal_run_queues_job_and_output_files``.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mcp_terminal.commands.terminal_get_status_command import TerminalGetStatusCommand
from mcp_terminal.commands.terminal_run_command import TerminalRunCommand
from mcp_terminal.services.command_history import CommandHistory, CommandRecord
from mcp_terminal.services.project_registry import ResolutionResult
from mcp_terminal import term_server
from mcp_terminal.services.output_reader import OutputReader
from mcp_terminal.services.sandbox_policy import (
    DEFAULT_NETWORK_SPEC,
    SandboxPolicy,
)

# C-011 queue/terminal status derivation: see tests/test_queue_result_semantics.py

_TERMINAL_GET_STATUS_KEYS = frozenset(
    {
        "job_id",
        "queue_status",
        "terminal_status",
        "exit_code",
        "timed_out",
        "stdout_file",
        "stderr_file",
        "stdout_bytes",
        "stderr_bytes",
    }
)


def _policy(**overrides: object):
    base = dict(
        project_id="00000000-0000-4000-8000-000000000001",
        execution_kind="argv",
        cwd=".",
        mode="read_only",
        network="none",
        image_profile="python_dev_3_12",
        command=None,
        argv=["echo", "ok"],
    )
    base.update(overrides)
    return SandboxPolicy().validate(**base)


# --- §21 unit-testable (SandboxPolicy / mount / network) ---


# Host path project_id rejection:
# tests/test_domain_invariants.py::test_sandbox_policy_rejects_host_path_project_id


def test_mvp_rejects_cwd_dotdot() -> None:
    """§21: cwd=.. is rejected."""
    result = _policy(cwd="..")
    assert not result.permitted
    assert result.error_code == "INVALID_CWD"


def test_mvp_rejects_absolute_cwd() -> None:
    """§21: absolute host-like cwd paths are rejected."""
    result = _policy(cwd="/workspace")
    assert not result.permitted
    assert result.error_code == "INVALID_CWD"


def test_mvp_rejects_missing_shell_command() -> None:
    """§21: invalid command (empty shell command) is rejected."""
    result = _policy(execution_kind="shell", command="   ", argv=None)
    assert not result.permitted
    assert result.error_code == "INVALID_COMMAND"


def test_mvp_rejects_empty_argv() -> None:
    """§21: invalid argv execution is rejected."""
    result = _policy(execution_kind="argv", argv=[])
    assert not result.permitted
    assert result.error_code == "INVALID_COMMAND"


def test_mvp_accepts_shell_and_argv_execution_kinds() -> None:
    """§21: terminal_run supports both shell and argv execution kinds."""
    shell = _policy(execution_kind="shell", command="echo hi", argv=None)
    argv = _policy(execution_kind="argv", command=None, argv=["echo", "hi"])
    assert shell.permitted
    assert argv.permitted


def test_mvp_default_mode_read_only_mount_is_readonly() -> None:
    """§21: default mode read_only — mount spec marks workspace readonly."""
    workspace = Path("/tmp/fake-workspace")
    spec, err = SandboxPolicy().build_mount_spec(
        workspace_source=workspace, mode="read_only", cwd="."
    )
    assert err is None
    assert spec is not None
    assert spec.workspace_readonly is True
    assert spec.workdir.startswith("/workspace")


def test_mvp_default_network_none_spec() -> None:
    """§21: default network is none."""
    net, err = SandboxPolicy().build_network_spec("none")
    assert err is None
    assert net == DEFAULT_NETWORK_SPEC
    assert net.mode == "none"
    assert net.allow_egress is False


# Docker.sock command rejection:
# tests/test_hostile_input_unit.py::test_hostile_rejects_docker_sock_path_in_shell_command


def test_mvp_terminal_get_status_response_shape(tmp_path: Path) -> None:
    """§21: result shape for terminal_get_status (verify via get_status + read)."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "000001.stdout.log").write_text("out\n", encoding="utf-8")
    (session_dir / "000001.stderr.log").write_text("", encoding="utf-8")
    record = SimpleNamespace(
        project_id="00000000-0000-4000-8000-000000000001",
        session_id="00000000-0000-4000-8000-000000000002",
        session_dir=session_dir,
    )
    cmd_record = CommandRecord(
        seq=1,
        job_id="job-accept",
        project_id=record.project_id,
        session_id=record.session_id,
        timestamp="2026-05-20T00:00:00Z",
        execution_kind="argv",
        command=None,
        argv=["true"],
        resolved_argv=["true"],
        cwd=".",
        mode="read_only",
        network="none",
        image_profile="python_dev_3_12",
        status="completed",
        exit_code=0,
        timed_out=False,
        stdout_file="000001.stdout.log",
        stderr_file="000001.stderr.log",
        meta_file="000001.meta.json",
    )
    cmd = TerminalGetStatusCommand()
    with (
        patch(
            "mcp_terminal.commands.terminal_get_status_command.resolve_session",
            return_value=(record, None),
        ),
        patch(
            "mcp_terminal.commands.terminal_get_status_command.get_session_store",
            return_value=SimpleNamespace(touch_activity=lambda *_a, **_k: None),
        ),
        patch.object(CommandHistory, "list_records", return_value=[cmd_record]),
    ):
        result = asyncio.run(
            cmd.execute(
                project_id=record.project_id,
                session_id=record.session_id,
                seq=1,
            )
        )
    assert result.success is True
    assert result.data is not None
    assert _TERMINAL_GET_STATUS_KEYS <= frozenset(result.data.keys())
    assert result.data["terminal_status"] == "success"
    assert result.data["stdout_file"] == "000001.stdout.log"
    reader = OutputReader(session_dir)
    payload, err = reader.read(1, "stdout")
    assert err is None
    assert payload == b"out\n"


# --- §21 requires live Docker (implemented in test_sandbox_docker_e2e.py) ---
# test_mvp_read_only_write_fails_in_container
#   → test_docker_read_only_blocks_workspace_write
# test_mvp_workspace_write_creates_file_in_container
#   → test_docker_workspace_write_creates_file
# test_mvp_project_mounted_only_at_workspace
#   → test_docker_project_mounted_only_at_workspace
# test_mvp_container_cannot_access_files_outside_mount
#   → test_docker_container_cannot_access_files_outside_mount
# test_mvp_timeout_cleans_up_container → test_docker_timeout_kills_long_sleep
# test_mvp_stdout_stderr_written_to_seq_files_not_inline
#   → test_docker_execution_job_writes_seq_output_files
# test_mvp_every_run_has_audit_record → test_docker_every_run_has_audit_record


_PROJECT_ID = "00000000-0000-4000-8000-000000000001"
_SESSION_ID = "00000000-0000-4000-8000-000000000002"


def test_mvp_terminal_run_appears_in_mcp_help() -> None:
    """§21: terminal_run is registered for adapter help (term_server command list)."""
    names = {cmd_cls.name for cmd_cls in term_server._TERMINAL_COMMAND_TYPES}
    assert "terminal_run" in names
    assert TerminalRunCommand in term_server._TERMINAL_COMMAND_TYPES


def test_mvp_terminal_run_rejects_unknown_project_id() -> None:
    """§21: terminal_run rejects unknown project_id."""
    cmd = TerminalRunCommand()
    not_found = ResolutionResult(
        success=False,
        project_dir=None,
        error_code="PROJECT_NOT_FOUND",
    )
    with (
        patch(
            "mcp_terminal.commands.terminal_run_command.registry_resolve_project",
            return_value=not_found,
        ),
        patch(
            "mcp_terminal.commands.terminal_run_command.enqueue_coroutine",
        ) as mock_enqueue,
    ):
        result = asyncio.run(
            cmd.execute(
                project_id="00000000-0000-4000-8000-000000000099",
                session_id=_SESSION_ID,
                execution_kind="argv",
                argv=["true"],
            )
        )
    assert result.success is False
    assert result.error == "PROJECT_NOT_FOUND"
    mock_enqueue.assert_not_called()


def test_mvp_terminal_run_rejects_invalid_session_id() -> None:
    """§21: terminal_run rejects missing or invalid session_id."""
    project_dir = Path("/tmp/fake-project")
    resolved = ResolutionResult(success=True, project_dir=project_dir)
    cmd = TerminalRunCommand()
    with (
        patch(
            "mcp_terminal.commands.terminal_run_command.registry_resolve_project",
            return_value=resolved,
        ),
        patch(
            "mcp_terminal.commands.terminal_run_command.resolve_session",
            return_value=(None, "INVALID_SESSION"),
        ),
        patch(
            "mcp_terminal.commands.terminal_run_command.enqueue_coroutine",
        ) as mock_enqueue,
    ):
        result = asyncio.run(
            cmd.execute(
                project_id=_PROJECT_ID,
                session_id="00000000-0000-4000-8000-000000000099",
                execution_kind="argv",
                argv=["true"],
            )
        )
    assert result.success is False
    assert result.error == "INVALID_SESSION"
    mock_enqueue.assert_not_called()
