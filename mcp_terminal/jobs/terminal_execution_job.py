"""
TerminalExecutionJob: queue job for sandbox container execution (C-009).

Session lifecycle: start container → load shell_state → exec → save state →
optionally stop container (unless keep_container).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from mcp_terminal.services.audit_writer import AuditWriter, session_audit_log_path
from mcp_terminal.services.command_history import CommandHistory
from mcp_terminal.services.container_runner import ContainerSpec
from mcp_terminal.services.session_container import SessionContainerExecutor
from mcp_terminal.services.shell_state import read_shell_state


@dataclass(frozen=True)
class JobParams:
    """Immutable parameters for one TerminalExecutionJob invocation."""

    project_id: str
    session_id: str
    seq: int
    session_dir: Path
    project_dir: Path
    container_spec: ContainerSpec
    timeout_seconds: int
    keep_container: bool = False
    effective_cwd: str = "."
    execution_kind: str = "shell"
    command: Optional[str] = None
    argv: Optional[List[str]] = None
    use_venv: bool = True


class TerminalExecutionJob:
    """Queue job that performs sandbox container execution (C-009).

    The run() method is called by the adapter queue worker in a background
    thread. It must never be called directly from request handlers.
    QueueResultSemantics (C-011): a completed job does not imply the
    terminal command succeeded; callers must check exit_code and timed_out.
    """

    def __init__(
        self,
        params: JobParams,
        executor: Optional[SessionContainerExecutor] = None,
    ) -> None:
        self._params = params
        self._executor = executor or SessionContainerExecutor()
        self._logger = logging.getLogger(__name__)

    def run(self) -> dict:
        """Execute the session container cycle and write output files."""
        p = self._params
        prefix = CommandHistory.seq_to_prefix(p.seq)
        meta_path = p.session_dir / f"{prefix}.meta.json"
        start_time = datetime.now(timezone.utc)

        exit_code, timed_out, status = self._executor.run(
            project_id=p.project_id,
            session_id=p.session_id,
            seq=p.seq,
            session_dir=p.session_dir,
            spec=p.container_spec,
            timeout_seconds=p.timeout_seconds,
            keep_container=p.keep_container,
            effective_cwd=p.effective_cwd,
            execution_kind=p.execution_kind,
            command=p.command,
            argv=p.argv,
            use_venv=p.use_venv,
        )

        meta = {
            "seq": p.seq,
            "status": status,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "keep_container": p.keep_container,
            "execution_target": "sandbox",
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        history = CommandHistory(p.session_dir)
        history.update_record(p.seq, status=status, exit_code=exit_code, timed_out=timed_out)

        stdout_path = p.session_dir / f"{prefix}.stdout.log"
        stderr_path = p.session_dir / f"{prefix}.stderr.log"
        finish_time = datetime.now(timezone.utc)
        shell = read_shell_state(p.session_dir)
        if p.execution_kind == "argv" and p.argv:
            resolved_argv: List[str] = list(p.argv)
        else:
            resolved_argv = list(p.container_spec.resolved_argv)
        spec = p.container_spec
        cmd_record = next(
            (r for r in history.list_records(limit=10000) if r.seq == p.seq),
            None,
        )
        audit_mode = cmd_record.mode if cmd_record else spec.mount_spec.mode
        audit_network = cmd_record.network if cmd_record else spec.network_spec
        audit_image = cmd_record.image_profile if cmd_record else "sandbox"
        AuditWriter(session_audit_log_path(p.session_dir)).write(
            project_id=p.project_id,
            session_id=p.session_id,
            seq=p.seq,
            project_dir=p.project_dir,
            command=p.command,
            resolved_argv=resolved_argv,
            cwd=p.effective_cwd,
            mode=audit_mode,
            network=audit_network,
            image_profile=audit_image,
            container_id=shell.container_id,
            start_time=start_time,
            finish_time=finish_time,
            exit_code=exit_code,
            timed_out=timed_out,
            stdout_file=f"{prefix}.stdout.log",
            stderr_file=f"{prefix}.stderr.log",
            stdout_bytes=stdout_path.stat().st_size if stdout_path.exists() else 0,
            stderr_bytes=stderr_path.stat().st_size if stderr_path.exists() else 0,
            policy_decision="executed" if status == "completed" else "failed",
            error_code=None,
            execution_target="sandbox",
            use_venv_resolved=p.use_venv,
        )

        self._logger.info(
            "Job complete seq=%d status=%s exit_code=%s timed_out=%s keep_container=%s",
            p.seq,
            status,
            exit_code,
            timed_out,
            p.keep_container,
        )
        return {"exit_code": exit_code, "timed_out": timed_out, "status": status}
