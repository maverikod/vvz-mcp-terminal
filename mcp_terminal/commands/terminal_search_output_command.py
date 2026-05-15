"""
terminal_search_output command for mcp_terminal (C-014, C-008).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.runtime_context import get_session_store
from mcp_terminal.services.output_reader import DEFAULT_MAX_MATCHES, OutputReader


class TerminalSearchOutputCommand(Command):
    """Regex search within one command output stream."""

    name: ClassVar[str] = "terminal_search_output"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = "Search stdout or stderr of one command for lines matching a regex."
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
                "seq": {"type": "integer"},
                "stream": {"type": "string", "enum": ["stdout", "stderr"]},
                "pattern": {"type": "string", "description": "Regex applied line-wise."},
                "max_matches": {
                    "type": "integer",
                    "default": DEFAULT_MAX_MATCHES,
                    "minimum": 1,
                    "maximum": 5000,
                },
            },
            "required": ["project_id", "session_id", "seq", "stream", "pattern"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", ""))
        session_id = str(kwargs.get("session_id", ""))
        seq = int(kwargs.get("seq", 0))
        stream = str(kwargs.get("stream", "stdout"))
        pattern = str(kwargs.get("pattern", ""))
        max_matches = int(kwargs.get("max_matches", DEFAULT_MAX_MATCHES))
        session_store = get_session_store()
        record = session_store.get_session(session_id)
        if record is None or record.project_id != project_id:
            return CommandResult(success=False, error="INVALID_SESSION")
        session_store.touch_activity(session_id)
        reader = OutputReader(record.session_dir)
        matches, err = reader.search(seq, stream, pattern, max_matches=max_matches)
        if err is not None:
            return CommandResult(success=False, error=str(err))
        assert matches is not None
        out: List[Dict[str, Any]] = [
            {"seq": m.seq, "stream": m.stream, "line_number": m.line_number, "text": m.text}
            for m in matches
        ]
        return CommandResult(success=True, data={"matches": out, "count": len(out)})
