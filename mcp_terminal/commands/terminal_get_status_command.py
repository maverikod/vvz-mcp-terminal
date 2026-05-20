"""
terminal_get_status command for mcp_terminal (C-014, C-011).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar, Dict, Optional, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.commands.session_resolve import resolve_session
from mcp_terminal.commands.terminal_get_status_metadata import (
    get_terminal_get_status_metadata,
)
from mcp_terminal.runtime_context import get_session_store
from mcp_terminal.services.command_history import CommandHistory
from mcp_terminal.services.output_reader import OutputReader


def _execution_target_from_meta(session_dir: Path, seq: int) -> Optional[str]:
    """Read execution_target from NNNNNN.meta.json; map legacy ``container`` to ``sandbox``."""
    prefix = CommandHistory.seq_to_prefix(seq)
    meta_path = session_dir / f"{prefix}.meta.json"
    if not meta_path.is_file():
        return None
    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    target = raw.get("execution_target")
    if not isinstance(target, str):
        return None
    if target == "container":
        return "sandbox"
    return target


class TerminalGetStatusCommand(Command):
    """MCP command: terminal_get_status (C-011 QueueResultSemantics)."""

    name: ClassVar[str] = "terminal_get_status"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = (
        "Return queue status and terminal command result for a command. "
        "Queue completed does not imply terminal success (C-011)."
    )
    category: ClassVar[str] = "custom"
    author: ClassVar[str] = "Vasiliy Zdanovskiy"
    email: ClassVar[str] = "vasilyvz@gmail.com"
    result_class: ClassVar[Type[CommandResult]] = CommandResult

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """JSON schema for terminal_get_status parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "session_id": {"type": "string"},
                "seq": {"type": "integer"},
            },
            "required": ["project_id", "session_id", "seq"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        """Return combined queue status and terminal command result (C-011)."""
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", ""))
        session_id = str(kwargs.get("session_id", ""))
        seq = int(kwargs.get("seq", 0))
        record, err = resolve_session(project_id, session_id)
        if err is not None:
            return CommandResult(success=False, error=err)
        session_store = get_session_store()
        session_store.touch_activity(record.project_id, record.session_id)
        history = CommandHistory(record.session_dir)
        all_records = history.list_records(limit=10000)
        cmd_record = next((r for r in all_records if r.seq == seq), None)
        if cmd_record is None:
            return CommandResult(success=False, error="NOT_FOUND")
        queue_status = cmd_record.status
        exit_code = cmd_record.exit_code
        timed_out = bool(cmd_record.timed_out)
        if queue_status == "completed" and exit_code == 0 and not timed_out:
            terminal_status = "success"
        elif queue_status == "completed" and timed_out:
            terminal_status = "timed_out"
        elif queue_status == "completed":
            terminal_status = "failure"
        else:
            terminal_status = queue_status
        reader = OutputReader(record.session_dir)
        stat = reader.stat(seq)
        execution_target = _execution_target_from_meta(record.session_dir, seq)
        data: Dict[str, Any] = {
            "job_id": cmd_record.job_id,
            "queue_status": queue_status,
            "terminal_status": terminal_status,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "stdout_file": stat.stdout_file,
            "stderr_file": stat.stderr_file,
            "stdout_bytes": stat.stdout_bytes,
            "stderr_bytes": stat.stderr_bytes,
        }
        if execution_target is not None:
            data["execution_target"] = execution_target
        return CommandResult(success=True, data=data)

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_terminal_get_status_metadata(cls)
