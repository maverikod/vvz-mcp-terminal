"""terminal_get_status: execution_target from meta.json."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mcp_terminal.commands.terminal_get_status_command import TerminalGetStatusCommand
from mcp_terminal.services.command_history import CommandHistory, CommandRecord


def test_terminal_get_status_returns_execution_target_from_meta(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    meta_path = session_dir / "000001.meta.json"
    meta_path.write_text(
        json.dumps({"execution_target": "host", "exit_code": 0, "timed_out": False}),
        encoding="utf-8",
    )
    record = SimpleNamespace(
        project_id="00000000-0000-4000-8000-000000000001",
        session_id="00000000-0000-4000-8000-000000000002",
        session_dir=session_dir,
    )
    cmd_record = CommandRecord(
        seq=1,
        job_id="job-1",
        project_id=record.project_id,
        session_id=record.session_id,
        timestamp="2026-01-01T00:00:00Z",
        execution_kind="shell",
        command="true",
        argv=None,
        resolved_argv=["bash", "-lc", "true"],
        cwd=".",
        mode="host",
        network="host",
        image_profile="host",
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
    assert result.data["execution_target"] == "host"


def test_terminal_get_status_maps_legacy_container_meta_to_sandbox(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "000001.meta.json").write_text(
        json.dumps({"execution_target": "container"}),
        encoding="utf-8",
    )
    record = SimpleNamespace(
        project_id="p",
        session_id="s",
        session_dir=session_dir,
    )
    cmd_record = CommandRecord(
        seq=1,
        job_id=None,
        project_id="p",
        session_id="s",
        timestamp="2026-01-01T00:00:00Z",
        execution_kind="shell",
        command="true",
        argv=None,
        resolved_argv=["true"],
        cwd=".",
        mode="read_only",
        network="none",
        image_profile="python_dev_3_12",
        status="pending",
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
        result = asyncio.run(cmd.execute(project_id="p", session_id="s", seq=1))

    assert result.success is True
    assert result.data is not None
    assert result.data["execution_target"] == "sandbox"
