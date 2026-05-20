"""
Audit record writer for mcp_terminal (C-012).

Creates immutable audit entries for every terminal_run invocation.
Must not record secret environment variable values.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional


def session_audit_log_path(session_dir: Path) -> Path:
    """Per-session append-only audit log (C-012)."""
    return session_dir / "audit.jsonl"


def allowed_commands_snapshot_hash(allowed_commands: FrozenSet[str]) -> str:
    """Stable hash of the active host allowlist at decision time."""
    payload = "\n".join(sorted(allowed_commands))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class AuditWriter:
    """Writes immutable AuditRecord entries for terminal executions (C-012)."""

    def __init__(self, audit_log_path: Path) -> None:
        self._log_path = audit_log_path
        self._logger = logging.getLogger(__name__)

    def write(
        self,
        *,
        project_id: str,
        session_id: str,
        seq: int,
        project_dir: Path,
        command: Optional[str],
        resolved_argv: List[Any],
        cwd: str,
        mode: str,
        network: str,
        image_profile: str,
        container_id: Optional[str],
        start_time: datetime,
        finish_time: datetime,
        exit_code: Optional[int],
        timed_out: bool,
        stdout_file: str,
        stderr_file: str,
        stdout_bytes: int,
        stderr_bytes: int,
        policy_decision: str,
        error_code: Optional[str],
        execution_target: str,
        resolved_cwd_on_host: Optional[str] = None,
        use_venv_resolved: Optional[bool] = None,
        allowed_commands_snapshot_hash: Optional[str] = None,
        policy_code: Optional[str] = None,
    ) -> str:
        """Write an immutable AuditRecord to the audit log.

        Secret environment variable values must never be passed to this method.
        Only environment variable names may appear in policy_decision summary.

        Args:
            project_dir: Used only for hashing; the hash is recorded, not the path.
            execution_target: ``sandbox``, ``host``, or ``attached`` (C-017).
            resolved_cwd_on_host: Project-relative cwd for host target (C-012).
            use_venv_resolved: Resolved venv flag for host/sandbox runs.
            allowed_commands_snapshot_hash: Host allowlist snapshot (C-012).
            policy_code: Stable ErrorContract code when the request was rejected.

        Returns:
            run_id (UUID4 string) of the written audit record.
        """
        run_id = str(uuid.uuid4())
        path_hash = hashlib.sha256(str(project_dir).encode()).hexdigest()[:16]
        record: Dict[str, Any] = {
            "run_id": run_id,
            "project_id": project_id,
            "session_id": session_id,
            "seq": seq,
            "project_dir_hash": path_hash,
            "command": command,
            "resolved_argv": resolved_argv,
            "cwd": cwd,
            "mode": mode,
            "network": network,
            "image_profile": image_profile,
            "container_id": container_id,
            "start_time": start_time.isoformat(),
            "finish_time": finish_time.isoformat(),
            "duration_seconds": (finish_time - start_time).total_seconds(),
            "exit_code": exit_code,
            "timed_out": timed_out,
            "stdout_file": stdout_file,
            "stderr_file": stderr_file,
            "stdout_bytes": stdout_bytes,
            "stderr_bytes": stderr_bytes,
            "policy_decision": policy_decision,
            "error_code": error_code,
            "execution_target": execution_target,
        }
        if resolved_cwd_on_host is not None:
            record["resolved_cwd_on_host"] = resolved_cwd_on_host
        if use_venv_resolved is not None:
            record["use_venv_resolved"] = use_venv_resolved
        if allowed_commands_snapshot_hash is not None:
            record["allowed_commands_snapshot_hash"] = allowed_commands_snapshot_hash
        if policy_code is not None:
            record["policy_code"] = policy_code
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return run_id
