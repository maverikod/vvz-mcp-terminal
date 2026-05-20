"""
TerminalHostExecutionJob: queue job for host-side command execution.

Separate from ``TerminalExecutionJob`` (Docker session container path).

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

from mcp_terminal.services.audit_writer import (
    AuditWriter,
    allowed_commands_snapshot_hash,
    session_audit_log_path,
)
from mcp_terminal.services.command_history import CommandHistory
from mcp_terminal.services.host_execution_config import get_host_execution_config
from mcp_terminal.services.host_session_executor import HostSessionExecutor


@dataclass(frozen=True)
class HostJobParams:
    """Immutable parameters for one TerminalHostExecutionJob invocation."""

    project_id: str
    session_id: str
    seq: int
    session_dir: Path
    project_dir: Path
    timeout_seconds: int
    effective_cwd: str = "."
    execution_kind: str = "shell"
    command: Optional[str] = None
    argv: Optional[List[str]] = None
    use_venv: bool = True


class TerminalHostExecutionJob:
    """Queue job that runs an allowlisted command on the host (not in Docker)."""

    def __init__(
        self,
        params: HostJobParams,
        executor: Optional[HostSessionExecutor] = None,
    ) -> None:
        self._params = params
        self._executor = executor or HostSessionExecutor()
        self._logger = logging.getLogger(__name__)

    def run(self) -> dict:
        """Execute on the host and write output/meta files."""
        p = self._params
        prefix = CommandHistory.seq_to_prefix(p.seq)
        meta_path = p.session_dir / f"{prefix}.meta.json"
        start_time = datetime.now(timezone.utc)

        exit_code, timed_out, status = self._executor.run(
            project_id=p.project_id,
            session_id=p.session_id,
            seq=p.seq,
            session_dir=p.session_dir,
            project_dir=p.project_dir,
            timeout_seconds=p.timeout_seconds,
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
            "execution_target": "host",
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        history = CommandHistory(p.session_dir)
        history.update_record(p.seq, status=status, exit_code=exit_code, timed_out=timed_out)

        stdout_path = p.session_dir / f"{prefix}.stdout.log"
        stderr_path = p.session_dir / f"{prefix}.stderr.log"
        finish_time = datetime.now(timezone.utc)
        he = get_host_execution_config()
        if p.execution_kind == "argv" and p.argv:
            resolved_argv: List[str] = list(p.argv)
        else:
            resolved_argv = ["bash", "-lc", p.command or "true"]
        AuditWriter(session_audit_log_path(p.session_dir)).write(
            project_id=p.project_id,
            session_id=p.session_id,
            seq=p.seq,
            project_dir=p.project_dir,
            command=p.command,
            resolved_argv=resolved_argv,
            cwd=p.effective_cwd,
            mode="host",
            network="host",
            image_profile="host",
            container_id=None,
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
            execution_target="host",
            resolved_cwd_on_host=p.effective_cwd,
            use_venv_resolved=p.use_venv,
            allowed_commands_snapshot_hash=allowed_commands_snapshot_hash(he.allowed_commands),
        )

        self._logger.info(
            "Host job complete seq=%d status=%s exit_code=%s timed_out=%s",
            p.seq,
            status,
            exit_code,
            timed_out,
        )
        return {"exit_code": exit_code, "timed_out": timed_out, "status": status}
