"""
terminal_get command for mcp_terminal (C-014).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.runtime_context import get_session_store
from mcp_terminal.services.command_history import CommandHistory


class TerminalGetCommand(Command):
    """MCP command: terminal_get."""

    name: ClassVar[str] = "terminal_get"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = "Return metadata for one command by exact seq."
    category: ClassVar[str] = "custom"
    author: ClassVar[str] = "Vasiliy Zdanovskiy"
    email: ClassVar[str] = "vasilyvz@gmail.com"
    result_class: ClassVar[Type[CommandResult]] = CommandResult

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """JSON schema for terminal_get parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project UUID4."},
                "session_id": {"type": "string", "description": "Session UUID4."},
                "seq": {
                    "type": "integer",
                    "description": "Session-local command sequence number.",
                },
            },
            "required": ["project_id", "session_id", "seq"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        """Return full CommandRecord for project_id + session_id + seq."""
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", ""))
        session_id = str(kwargs.get("session_id", ""))
        seq = int(kwargs.get("seq", 0))
        session_store = get_session_store()
        record = session_store.get_session(session_id)
        if record is None or record.project_id != project_id:
            return CommandResult(success=False, error="INVALID_SESSION")
        session_store.touch_activity(session_id)
        history = CommandHistory(record.session_dir)
        all_records = history.list_records(limit=10000)
        for r in all_records:
            if r.seq == seq:
                return CommandResult(
                    success=True,
                    data={
                        "seq": r.seq,
                        "timestamp": r.timestamp,
                        "status": r.status,
                        "exit_code": r.exit_code,
                        "timed_out": r.timed_out,
                        "execution_kind": r.execution_kind,
                        "command": r.command,
                        "argv": r.argv,
                        "resolved_argv": r.resolved_argv,
                        "cwd": r.cwd,
                        "mode": r.mode,
                        "network": r.network,
                        "image_profile": r.image_profile,
                        "stdout_file": r.stdout_file,
                        "stderr_file": r.stderr_file,
                        "meta_file": r.meta_file,
                        "job_id": r.job_id,
                    },
                )
        return CommandResult(success=False, error="NOT_FOUND")
