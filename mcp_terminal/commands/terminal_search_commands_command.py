"""
terminal_search_commands command for mcp_terminal (C-014).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from typing import Any, ClassVar, Dict, List, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.commands.session_resolve import resolve_session
from mcp_terminal.runtime_context import get_session_store
from mcp_terminal.services.command_history import CommandHistory


class TerminalSearchCommandsCommand(Command):
    """Search command history metadata by regex (C-014)."""

    name: ClassVar[str] = "terminal_search_commands"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = "Search command history metadata by regex."
    category: ClassVar[str] = "custom"
    author: ClassVar[str] = "Vasiliy Zdanovskiy"
    email: ClassVar[str] = "vasilyvz@gmail.com"
    result_class: ClassVar[Type[CommandResult]] = CommandResult

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "session_id": {"type": "string"},
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern applied to command text and status.",
                },
                "limit": {"type": "integer", "default": 25, "minimum": 1, "maximum": 500},
            },
            "required": ["project_id", "session_id", "pattern"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        """Search command metadata for lines matching pattern."""
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", ""))
        session_id = str(kwargs.get("session_id", ""))
        pattern = str(kwargs.get("pattern", ""))
        limit = int(kwargs.get("limit", 25))
        record, err = resolve_session(project_id, session_id)
        if err is not None:
            return CommandResult(success=False, error=err)
        session_store = get_session_store()
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return CommandResult(success=False, error=f"INVALID_PATTERN: {exc}")
        session_store.touch_activity(record.project_id, record.session_id)
        history = CommandHistory(record.session_dir)
        all_records = history.list_records(limit=10000)
        matches: List[Dict[str, Any]] = []
        for r in all_records:
            display = r.command or " ".join(r.argv or [])
            if regex.search(display) or regex.search(r.status):
                matches.append(
                    {
                        "seq": r.seq,
                        "timestamp": r.timestamp,
                        "status": r.status,
                        "exit_code": r.exit_code,
                        "command_display": display,
                    }
                )
                if len(matches) >= limit:
                    break
        return CommandResult(success=True, data=matches)  # type: ignore[arg-type]
