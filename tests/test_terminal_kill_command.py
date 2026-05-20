"""Integration tests for terminal_kill command."""

from __future__ import annotations

import asyncio
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from mcp_terminal.commands.terminal_kill_command import TerminalKillCommand
from mcp_terminal.services import running_terminal_jobs as rtj
from mcp_terminal.services.command_history import CommandHistory, CommandRecord

_PROJECT_ID = "00000000-0000-4000-8000-000000000001"
_SESSION_ID = "00000000-0000-4000-8000-000000000002"


def _pending_record(*, seq: int = 1) -> CommandRecord:
    prefix = CommandHistory.seq_to_prefix(seq)
    return CommandRecord(
        seq=seq,
        job_id="job-1",
        project_id=_PROJECT_ID,
        session_id=_SESSION_ID,
        timestamp="2026-01-01T00:00:00Z",
        execution_kind="shell",
        command="sleep 999",
        argv=None,
        resolved_argv=["bash", "-lc", "sleep 999"],
        cwd=".",
        mode="read_only",
        network="none",
        image_profile="python_dev_3_12",
        status="pending",
        stdout_file=f"{prefix}.stdout.log",
        stderr_file=f"{prefix}.stderr.log",
        meta_file=f"{prefix}.meta.json",
    )


def _session_record(session_dir) -> SimpleNamespace:
    return SimpleNamespace(
        project_id=_PROJECT_ID,
        session_id=_SESSION_ID,
        session_dir=session_dir,
    )


def test_terminal_kill_sends_sigkill_when_job_registered(tmp_path) -> None:
    """Pending history record + registered subprocess → success and kill()."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    CommandHistory(session_dir).append_record(_pending_record())

    proc = MagicMock(spec=subprocess.Popen)
    rtj.register(_SESSION_ID, 1, proc)
    try:
        cmd = TerminalKillCommand()
        with (
            patch(
                "mcp_terminal.commands.terminal_kill_command.resolve_session",
                return_value=(_session_record(session_dir), None),
            ),
            patch(
                "mcp_terminal.commands.terminal_kill_command.get_session_store",
                return_value=SimpleNamespace(touch_activity=lambda *_a, **_k: None),
            ),
        ):
            result = asyncio.run(
                cmd.execute(
                    project_id=_PROJECT_ID,
                    session_id=_SESSION_ID,
                    seq=1,
                )
            )
    finally:
        rtj.unregister(_SESSION_ID, 1)

    assert result.success is True
    assert result.data is not None
    assert result.data["killed"] is True
    assert result.data["signal"] == "SIGKILL"
    proc.kill.assert_called_once()


def test_terminal_kill_kill_not_applied_without_registered_job(tmp_path) -> None:
    """Pending record but no running_terminal_jobs entry → KILL_NOT_APPLIED."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    CommandHistory(session_dir).append_record(_pending_record())

    cmd = TerminalKillCommand()
    with (
        patch(
            "mcp_terminal.commands.terminal_kill_command.resolve_session",
            return_value=(_session_record(session_dir), None),
        ),
        patch(
            "mcp_terminal.commands.terminal_kill_command.get_session_store",
            return_value=SimpleNamespace(touch_activity=lambda *_a, **_k: None),
        ),
    ):
        result = asyncio.run(
            cmd.execute(
                project_id=_PROJECT_ID,
                session_id=_SESSION_ID,
                seq=1,
            )
        )

    assert result.success is False
    assert result.error == "KILL_NOT_APPLIED"
    assert result.data is not None
    assert "No active subprocess" in (result.data.get("detail") or "")
