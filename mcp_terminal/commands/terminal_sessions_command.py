"""
terminal_sessions command for mcp_terminal (C-014).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.runtime_context import get_session_store


class TerminalSessionsCommand(Command):
    """Lists terminal sessions for a project (C-014)."""

    name: ClassVar[str] = "terminal_sessions"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = "Return all terminal sessions for a project."
    category: ClassVar[str] = "custom"
    author: ClassVar[str] = "Vasiliy Zdanovskiy"
    email: ClassVar[str] = "vasilyvz@gmail.com"
    result_class: ClassVar[Type[CommandResult]] = CommandResult

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return input schema for terminal_sessions."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project UUID4."},
                "limit": {
                    "type": "integer",
                    "default": 25,
                    "minimum": 1,
                    "maximum": 500,
                    "description": "Maximum sessions to return.",
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        """Return session summaries for the given project_id."""
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", ""))
        limit = int(kwargs.get("limit", 25))
        session_store = get_session_store()
        sessions = session_store.list_sessions(project_id)
        summaries = [
            {
                "session_id": r.session_id,
                "project_id": r.project_id,
                "created_at": r.created_at.isoformat(),
                "last_activity_at": r.last_activity_at.isoformat(),
                "status": r.status,
                "workspace_write": r.workspace_write,
            }
            for r in sessions[:limit]
        ]
        return CommandResult(success=True, data=summaries)  # type: ignore[arg-type]
