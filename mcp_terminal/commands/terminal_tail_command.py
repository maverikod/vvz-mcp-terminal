"""
terminal_tail command for mcp_terminal (C-014, C-008).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.commands.session_resolve import resolve_session
from mcp_terminal.commands.terminal_tail_metadata import get_terminal_tail_metadata
from mcp_terminal.runtime_context import get_session_store
from mcp_terminal.services.host_exec_store import resolve_host_exec_run
from mcp_terminal.services.output_reader import DEFAULT_TAIL_LINES, OutputReader


class TerminalTailCommand(Command):
    """Return the last N lines of stdout or stderr for one seq (C-008)."""

    name: ClassVar[str] = "terminal_tail"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = "Return the last N lines from a command output stream."
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
                "host_run_id": {"type": "string"},
                "seq": {"type": "integer"},
                "stream": {"type": "string", "enum": ["stdout", "stderr"]},
                "lines": {
                    "type": "integer",
                    "default": DEFAULT_TAIL_LINES,
                    "minimum": 1,
                    "maximum": 10000,
                    "description": "Number of trailing lines to return.",
                },
            },
            "required": ["seq", "stream"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_terminal_tail_metadata(cls)

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", ""))
        session_id = str(kwargs.get("session_id", ""))
        host_run_id = str(kwargs.get("host_run_id", "")).strip()
        seq = int(kwargs.get("seq", 0))
        stream = str(kwargs.get("stream", "stdout"))
        lines = int(kwargs.get("lines", DEFAULT_TAIL_LINES))
        if host_run_id:
            host_run = resolve_host_exec_run(host_run_id)
            if host_run is None:
                return CommandResult(success=False, error="NOT_FOUND")
            session_dir = host_run.run_dir
        else:
            record, err = resolve_session(project_id, session_id)
            if err is not None:
                return CommandResult(success=False, error=err)
            session_store = get_session_store()
            session_store.touch_activity(record.project_id, record.session_id)
            session_dir = record.session_dir
        reader = OutputReader(session_dir)
        tail_lines, err = reader.tail(seq, stream, lines=lines)
        if err is not None:
            return CommandResult(success=False, error=err)
        assert tail_lines is not None
        return CommandResult(success=True, data={"lines": tail_lines, "count": len(tail_lines)})
