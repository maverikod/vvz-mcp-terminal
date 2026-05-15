"""
terminal_delete command for mcp_terminal (C-014, C-005).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.runtime_context import get_session_store


class TerminalDeleteCommand(Command):
    """Delete a terminal session directory and unregister it."""

    name: ClassVar[str] = "terminal_delete"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = (
        "Delete a terminal session. Requires session_id; project_id, when set, "
        "must match the session's project."
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
                "session_id": {"type": "string", "description": "Session UUID4 to delete."},
                "project_id": {
                    "type": "string",
                    "description": "Optional; when provided, must match the session's project.",
                },
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, delete even if the session is running.",
                },
            },
            "required": ["session_id"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        session_id = str(kwargs.get("session_id", "")).strip()
        project_id_opt = kwargs.get("project_id")
        force = bool(kwargs.get("force", False))
        session_store = get_session_store()
        record = session_store.get_session(session_id)
        if record is None:
            return CommandResult(success=True, data={"deleted": True, "session_id": session_id})
        if project_id_opt is not None and str(project_id_opt).strip() != record.project_id:
            return CommandResult(success=False, error="INVALID_SESSION")
        ok = session_store.delete_session(session_id, force=force)
        if not ok:
            return CommandResult(success=False, error="SESSION_RUNNING")
        return CommandResult(success=True, data={"deleted": True, "session_id": session_id})
