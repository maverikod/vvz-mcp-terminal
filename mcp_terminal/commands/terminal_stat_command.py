"""
terminal_stat command for mcp_terminal (C-014, C-008).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.runtime_context import get_session_store
from mcp_terminal.services.output_reader import OutputReader


class TerminalStatCommand(Command):
    """Return output file sizes for one command seq (no content read)."""

    name: ClassVar[str] = "terminal_stat"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = "Return stdout/stderr file names and sizes for a command."
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
            },
            "required": ["project_id", "session_id", "seq"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", ""))
        session_id = str(kwargs.get("session_id", ""))
        seq = int(kwargs.get("seq", 0))
        session_store = get_session_store()
        record = session_store.get_session(session_id)
        if record is None or record.project_id != project_id:
            return CommandResult(success=False, error="INVALID_SESSION")
        session_store.touch_activity(session_id)
        reader = OutputReader(record.session_dir)
        stat = reader.stat(seq)
        return CommandResult(
            success=True,
            data={
                "seq": stat.seq,
                "stdout_file": stat.stdout_file,
                "stderr_file": stat.stderr_file,
                "stdout_bytes": stat.stdout_bytes,
                "stderr_bytes": stat.stderr_bytes,
            },
        )
