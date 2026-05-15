"""
terminal_list command for mcp_terminal (C-014).

Returns recent command history for a terminal session.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.runtime_context import get_session_store
from mcp_terminal.services.command_history import CommandHistory


class TerminalListCommand(Command):
    """MCP command: terminal_list."""

    name: ClassVar[str] = "terminal_list"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = (
        "Return recent command history for a terminal session, "
        "ordered descending by launch timestamp."
    )
    category: ClassVar[str] = "custom"
    author: ClassVar[str] = "Vasiliy Zdanovskiy"
    email: ClassVar[str] = "vasilyvz@gmail.com"
    result_class: ClassVar[Type[CommandResult]] = CommandResult

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """JSON schema for terminal_list parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID4 identifier.",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session UUID4 identifier.",
                },
                "limit": {
                    "type": "integer",
                    "default": 25,
                    "minimum": 1,
                    "maximum": 200,
                    "description": "Maximum number of commands to return.",
                },
            },
            "required": ["project_id", "session_id"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        """Execute terminal_list and return command history."""
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", ""))
        session_id = str(kwargs.get("session_id", ""))
        limit = int(kwargs.get("limit", 25))
        session_store = get_session_store()
        record = session_store.get_session(session_id)
        if record is None or record.project_id != project_id:
            return CommandResult(success=False, error="INVALID_SESSION")
        session_store.touch_activity(session_id)
        history = CommandHistory(record.session_dir)
        records = history.list_records(limit=limit)
        summaries: List[Dict[str, Any]] = [
            {
                "seq": r.seq,
                "timestamp": r.timestamp,
                "status": r.status,
                "exit_code": r.exit_code,
                "execution_kind": r.execution_kind,
                "command_display": r.command or " ".join(r.argv or []),
            }
            for r in records
        ]
        return CommandResult(success=True, data=summaries)  # type: ignore[arg-type]
