"""
terminal_delete command for mcp_terminal (C-014, C-005).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.commands.session_resolve import resolve_session
from mcp_terminal.runtime_context import get_session_store


class TerminalDeleteCommand(Command):
    """Delete a terminal session directory and unregister it."""

    name: ClassVar[str] = "terminal_delete"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = (
        "Delete a terminal session for the (project_id, session_id) composite key."
    )
    category: ClassVar[str] = "custom"
    author: ClassVar[str] = "Vasiliy Zdanovskiy"
    email: ClassVar[str] = "vasilyvz@gmail.com"
    result_class: ClassVar[Type[CommandResult]] = CommandResult

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project UUID4."},
                "session_id": {"type": "string", "description": "Session UUID4."},
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, delete even if the session is running.",
                },
            },
            "required": ["project_id", "session_id"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", ""))
        session_id = str(kwargs.get("session_id", ""))
        force = bool(kwargs.get("force", False))
        record, err = resolve_session(project_id, session_id)
        if err == "INVALID_SESSION":
            return CommandResult(
                success=True,
                data={"deleted": True, "session_id": session_id, "project_id": project_id},
            )
        if err is not None:
            return CommandResult(success=False, error=err)
        assert record is not None
        session_store = get_session_store()
        ok = session_store.delete_session(record.project_id, record.session_id, force=force)
        if not ok:
            return CommandResult(success=False, error="SESSION_RUNNING")
        return CommandResult(
            success=True,
            data={"deleted": True, "session_id": session_id, "project_id": project_id},
        )
