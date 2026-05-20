"""
Enqueue host-side terminal runs (``terminal_run_host`` only).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from mcp_proxy_adapter.commands.base import CommandResult
from mcp_proxy_adapter.core.job_manager import enqueue_coroutine

from mcp_terminal.errors import ErrorCode
from mcp_terminal.jobs.terminal_host_execution_job import HostJobParams, TerminalHostExecutionJob
from mcp_terminal.services.audit_writer import (
    AuditWriter,
    allowed_commands_snapshot_hash,
    session_audit_log_path,
)
from mcp_terminal.services.command_history import CommandHistory, CommandRecord
from mcp_terminal.services.host_execution_config import (
    get_host_execution_config,
    validate_host_run_request,
)
from mcp_terminal.services.session_store import SessionRecord


async def enqueue_host_terminal_run(
    *,
    project_id: str,
    session_id: str,
    srec: SessionRecord,
    execution_kind: str,
    cmd_str: Optional[str],
    argv_list: Optional[List[str]],
    effective_cwd: str,
    timeout_seconds: int,
    use_venv: bool,
    project_dir: Path,
    session_store: Any,
) -> CommandResult:
    """Allocate seq, append history, and queue ``TerminalHostExecutionJob``."""
    validation = validate_host_run_request(execution_kind, cmd_str, argv_list)
    if not validation.ok:
        he = get_host_execution_config()
        now = datetime.now(timezone.utc)
        if execution_kind == "argv" and argv_list:
            reject_argv: List[str] = list(argv_list)
        else:
            reject_argv = ["bash", "-lc", cmd_str or ""]
        AuditWriter(session_audit_log_path(srec.session_dir)).write(
            project_id=project_id,
            session_id=session_id,
            seq=0,
            project_dir=project_dir,
            command=cmd_str,
            resolved_argv=reject_argv,
            cwd=effective_cwd,
            mode="host",
            network="host",
            image_profile="host",
            container_id=None,
            start_time=now,
            finish_time=now,
            exit_code=None,
            timed_out=False,
            stdout_file="",
            stderr_file="",
            stdout_bytes=0,
            stderr_bytes=0,
            policy_decision="rejected",
            error_code=validation.error_code,
            execution_target="host",
            resolved_cwd_on_host=effective_cwd,
            use_venv_resolved=use_venv,
            allowed_commands_snapshot_hash=allowed_commands_snapshot_hash(he.allowed_commands),
            policy_code=validation.error_code,
        )
        return CommandResult(
            success=False,
            error=validation.error_code or ErrorCode.HOST_COMMAND_NOT_ALLOWED,
        )

    session_store.touch_activity(project_id, session_id)
    history = CommandHistory(srec.session_dir)
    seq = history.allocate_seq()
    stdout_file, stderr_file, meta_file = history.pre_create_output_files(seq)
    ts = datetime.now(timezone.utc).isoformat()

    if execution_kind == "argv" and argv_list:
        resolved_argv = list(argv_list)
    else:
        resolved_argv = ["bash", "-lc", cmd_str or "true"]

    record = CommandRecord(
        seq=seq,
        job_id=None,
        project_id=project_id,
        session_id=session_id,
        timestamp=ts,
        execution_kind=execution_kind,
        command=cmd_str if execution_kind == "shell" else None,
        argv=argv_list if execution_kind == "argv" else None,
        resolved_argv=resolved_argv,
        cwd=effective_cwd,
        mode="host",
        network="host",
        image_profile="host",
        status="pending",
        stdout_file=stdout_file,
        stderr_file=stderr_file,
        meta_file=meta_file,
    )
    history.append_record(record)

    job_params = HostJobParams(
        project_id=project_id,
        session_id=session_id,
        seq=seq,
        session_dir=srec.session_dir,
        project_dir=project_dir.resolve(),
        timeout_seconds=timeout_seconds,
        effective_cwd=effective_cwd,
        execution_kind=execution_kind,
        command=cmd_str if execution_kind == "shell" else None,
        argv=argv_list if execution_kind == "argv" else None,
        use_venv=use_venv,
    )
    job = TerminalHostExecutionJob(job_params)

    async def _run_sync() -> dict:
        return await asyncio.to_thread(job.run)

    job_id = enqueue_coroutine(_run_sync())
    history.update_record(seq, status="pending", job_id=job_id)

    return CommandResult(
        success=True,
        data={
            "job_id": job_id,
            "seq": seq,
            "stdout_file": stdout_file,
            "stderr_file": stderr_file,
            "meta_file": meta_file,
            "cwd": effective_cwd,
            "use_venv": use_venv,
            "execution_target": "host",
        },
    )
