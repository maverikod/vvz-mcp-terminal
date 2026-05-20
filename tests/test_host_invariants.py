"""Host execution invariants H-1..H-5, H-8..H-11 (tech_spec §28.7)."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from mcp_terminal.config.host_execution_schema import HOST_EXECUTION_EMPTY_ALLOWLIST_LOG
from mcp_terminal.errors import ErrorCode
from mcp_terminal.jobs.terminal_host_execution_job import HostJobParams, TerminalHostExecutionJob
from mcp_terminal.services.audit_writer import allowed_commands_snapshot_hash
from mcp_terminal.services.command_history import CommandHistory
from mcp_terminal.services.host_execution_config import (
    HostCommandValidation,
    HostExecutionConfig,
    validate_host_argv_command,
    validate_host_run_request,
    validate_host_shell_command,
    warn_if_host_execution_enabled_without_commands,
)
from mcp_terminal.commands.terminal_run_host_command import TerminalRunHostCommand
from mcp_terminal.services.host_run_service import enqueue_host_terminal_run
from mcp_terminal.services.host_session_executor import HostSessionExecutor
from mcp_terminal.services.shell_state import (
    ShellState,
    normalize_cwd,
    read_shell_state,
    resolve_cwd,
    write_shell_state,
)

_HE_CFG = HostExecutionConfig(
    enabled=True, allowed_commands=frozenset({"pytest", "git", "true", "sleep"})
)


def _patch_host_config(cfg: HostExecutionConfig):
    return patch(
        "mcp_terminal.services.host_execution_config.get_host_execution_config",
        return_value=cfg,
    )


def _patch_host_config_executor(cfg: HostExecutionConfig):
    return patch(
        "mcp_terminal.services.host_session_executor.get_host_execution_config",
        return_value=cfg,
    )


# --- H-1: disabled gate ---


def test_h1_disabled_gate_rejects_without_queueing_job(tmp_path: Path) -> None:
    """H-1: disabled host execution returns HOST_EXECUTION_DISABLED and never enqueues."""
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
            result = await enqueue_host_terminal_run(
                project_id="p",
                session_id="s",
                srec=srec,
                execution_kind="argv",
                cmd_str=None,
                argv_list=["true"],
                effective_cwd=".",
                timeout_seconds=30,
                use_venv=False,
                project_dir=project_dir,
                session_store=session_store,
            )
        assert result.success is False
        assert result.error == ErrorCode.HOST_EXECUTION_DISABLED
        mock_enqueue.assert_not_called()
        assert not (session_dir / "history.jsonl").exists()

    asyncio.run(_run())


def test_h1_validate_host_run_request_disabled() -> None:
    """H-1: validate_host_run_request surfaces HOST_EXECUTION_DISABLED."""
    with _patch_host_config(
        HostExecutionConfig(enabled=False, allowed_commands=frozenset({"true"})),
    ):
        v = validate_host_run_request("argv", None, ["true"])
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_EXECUTION_DISABLED


# --- H-2: empty allowlist ---


def test_h2_empty_allowlist_rejects_request() -> None:
    """H-2: enabled with empty allowlist rejects every terminal_run_host request."""
    with _patch_host_config(HostExecutionConfig(enabled=True, allowed_commands=frozenset())):
        v = validate_host_run_request("argv", None, ["true"])
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_EXECUTION_DISABLED


def test_h2_empty_allowlist_startup_warning(caplog: pytest.LogCaptureFixture) -> None:
    """H-2: startup logs warning when enabled=true and allowed_commands=[]."""
    cfg = {"terminal": {"host_execution": {"enabled": True, "allowed_commands": []}}}
    with caplog.at_level(logging.WARNING):
        warn_if_host_execution_enabled_without_commands(cfg)
    assert HOST_EXECUTION_EMPTY_ALLOWLIST_LOG in caplog.text


# --- H-3 / H-4 / H-5 (extend) ---


def test_h3_hard_forbidden_beats_allowlist_sudo_argv() -> None:
    """H-3: hard-forbidden sudo rejected even when listed in allowed_commands."""
    allowed = frozenset({"sudo", "pytest"})
    v = validate_host_argv_command(["sudo", "apt", "update"], allowed)
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_FORBIDDEN_COMMAND


def test_h4_forbidden_pattern_in_here_string_operand() -> None:
    """H-4: forbidden substring in here-string operand is detected."""
    allowed = frozenset({"pytest"})
    command = "pytest -q <<< --pid=host"
    v = validate_host_shell_command(command, allowed)
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_FORBIDDEN_COMMAND
    detail = v.detail or ""
    assert "heredoc" in detail or "here-string" in detail
    assert "--pid=host" in detail


def test_h4_forbidden_pattern_in_command_text() -> None:
    """H-4: forbidden substring in command segment text is detected."""
    allowed = frozenset({"pytest"})
    v = validate_host_shell_command("pytest --pid=host -q", allowed)
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_FORBIDDEN_COMMAND
    assert "segment" in (v.detail or "") or "command" in (v.detail or "")


def test_h5_docker_path_manipulation_still_forbidden() -> None:
    """H-5: /usr/bin/docker is forbidden regardless of allowlist."""
    allowed = frozenset({"docker", "pytest"})
    v = validate_host_shell_command("/usr/bin/docker ps", allowed)
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_FORBIDDEN_COMMAND


def test_h5_podman_relative_path_still_forbidden() -> None:
    """H-5: ./podman path manipulation remains HOST_FORBIDDEN_COMMAND."""
    allowed = frozenset({"podman"})
    v = validate_host_shell_command("./podman ps", allowed)
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_FORBIDDEN_COMMAND


# --- H-6: invalid cwd rejected before host spawn ---


@pytest.mark.parametrize(
    "bad_cwd",
    ["/absolute/path", "../escape", "foo/../../outside"],
)
def test_h6_resolve_cwd_rejects_absolute_and_dotdot(tmp_path: Path, bad_cwd: str) -> None:
    """H-6: absolute or ..-bearing cwd yields INVALID_CWD via resolve_cwd."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    cwd, err = resolve_cwd(session_dir, bad_cwd)
    assert cwd is None
    assert err == "INVALID_CWD"


def test_h6_terminal_run_host_rejects_invalid_cwd_before_enqueue(tmp_path: Path) -> None:
    """H-6: terminal_run_host returns INVALID_CWD and never enqueues host job."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    srec = SimpleNamespace(session_dir=session_dir)
    resolved = SimpleNamespace(success=True, project_dir=project_dir, error_code=None)

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
            "mcp_terminal.commands.terminal_run_host_command.get_session_store",
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
    assert not (session_dir / "history.jsonl").exists()


# --- H-7: cwd cannot escape project root via normalization ---


@pytest.mark.parametrize(
    "bad_cwd",
    [
        "/etc/passwd",
        "../secret",
        "src/../../../etc",
        "a/..",
    ],
)
def test_h7_normalize_cwd_rejects_escape_paths(bad_cwd: str) -> None:
    """H-7: normalize_cwd rejects paths that would leave the project root."""
    with pytest.raises(ValueError, match="relative|\\.\\."):
        normalize_cwd(bad_cwd)


def test_h7_resolve_cwd_accepts_in_project_relative_paths(tmp_path: Path) -> None:
    """H-7: project-relative cwd segments resolve without error."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    for rel in (".", "src", "src/pkg", "tests/unit"):
        cwd, err = resolve_cwd(session_dir, rel)
        assert err is None
        assert cwd == normalize_cwd(rel)


# --- H-8: shell_state not corrupted on fail ---


def test_h8_validation_failure_preserves_shell_state(tmp_path: Path) -> None:
    """H-8: rejected host command does not corrupt shell_state.json."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    write_shell_state(session_dir, ShellState(cwd="keep-me", use_venv=False))
    before = (session_dir / "shell_state.json").read_text(encoding="utf-8")

    with (
        _patch_host_config_executor(_HE_CFG),
        patch(
            "mcp_terminal.services.host_session_executor.validate_host_run_request",
            return_value=HostCommandValidation(
                ok=False,
                error_code=ErrorCode.HOST_FORBIDDEN_COMMAND,
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
            command="docker ps",
            argv=None,
            use_venv=False,
        )

    assert status == "failed"
    assert exit_code is None
    assert not timed_out
    after = (session_dir / "shell_state.json").read_text(encoding="utf-8")
    assert after == before
    assert read_shell_state(session_dir).cwd == "keep-me"


def test_h8_failing_command_keeps_valid_shell_state(tmp_path: Path) -> None:
    """H-8: non-zero exit leaves shell_state.json valid and cwd unchanged when cd fails."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    write_shell_state(session_dir, ShellState(cwd=".", use_venv=False))

    with (
        _patch_host_config_executor(_HE_CFG),
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
            command="cd /nonexistent-dir-for-test && true",
            argv=None,
            use_venv=False,
        )

    assert status == "completed"
    assert exit_code != 0
    assert not timed_out
    state = read_shell_state(session_dir)
    assert state.cwd == "."
    raw = json.loads((session_dir / "shell_state.json").read_text(encoding="utf-8"))
    assert raw["version"] == 1
    assert isinstance(raw["cwd"], str)


# --- H-9: basename case-insensitive allowlist ---


def test_h9_basename_case_insensitive_argv() -> None:
    """H-9: allowlist match is case-insensitive for argv basename."""
    allowed = frozenset({"PyTest"})
    v = validate_host_argv_command(["pytest", "-q"], allowed)
    assert v.ok


def test_h9_basename_case_insensitive_shell_segment() -> None:
    """H-9: allowlist match is case-insensitive for shell segment executable."""
    allowed = frozenset({"GIT"})
    v = validate_host_shell_command("git status", allowed)
    assert v.ok


# H-10 shared session sequence space:
# tests/test_host_execution_integration.py::test_h10_sandbox_and_host_share_monotonic_seq


# --- H-11: timeout ---


def test_h11_timeout_kills_runaway_host_process(tmp_path: Path) -> None:
    """H-11: job timeout terminates host process and records timed_out=true."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()

    with (
        _patch_host_config(_HE_CFG),
        _patch_host_config_executor(_HE_CFG),
        patch(
            "mcp_terminal.jobs.terminal_host_execution_job.get_host_execution_config",
            return_value=_HE_CFG,
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
                timeout_seconds=1,
                execution_kind="shell",
                command="sleep 30",
                use_venv=False,
            )
        )
        job.run()

    meta = json.loads((session_dir / "000001.meta.json").read_text(encoding="utf-8"))
    assert meta["timed_out"] is True
    assert meta["execution_target"] == "host"

    history = CommandHistory(session_dir)
    records = history.list_records(limit=10)
    assert len(records) == 0  # job does not append history; meta is source of truth

    audit_lines = (session_dir / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert audit_lines
    audit = json.loads(audit_lines[-1])
    assert audit["timed_out"] is True
    assert audit["execution_target"] == "host"
    assert audit["allowed_commands_snapshot_hash"] == allowed_commands_snapshot_hash(
        _HE_CFG.allowed_commands
    )
