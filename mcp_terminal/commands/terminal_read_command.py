"""
terminal_read command for mcp_terminal (C-014, C-008).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.runtime_context import get_session_store
from mcp_terminal.services.output_reader import DEFAULT_MAX_BYTES, OutputReader


class TerminalReadCommand(Command):
    """Read a slice of stdout or stderr for one command seq (C-008)."""

    name: ClassVar[str] = "terminal_read"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = "Read bytes from a command output stream (stdout or stderr)."
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
                "stream": {
                    "type": "string",
                    "enum": ["stdout", "stderr"],
                    "description": "Which output stream to read.",
                },
                "offset": {
                    "type": "integer",
                    "default": 0,
                    "minimum": 0,
                    "description": "Byte offset into the stream.",
                },
                "max_bytes": {
                    "type": "integer",
                    "default": DEFAULT_MAX_BYTES,
                    "minimum": 1,
                    "maximum": 1048576,
                    "description": "Maximum bytes to return.",
                },
            },
            "required": ["project_id", "session_id", "seq", "stream"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", ""))
        session_id = str(kwargs.get("session_id", ""))
        seq = int(kwargs.get("seq", 0))
        stream = str(kwargs.get("stream", "stdout"))
        offset = int(kwargs.get("offset", 0))
        max_bytes = int(kwargs.get("max_bytes", DEFAULT_MAX_BYTES))
        session_store = get_session_store()
        record = session_store.get_session(session_id)
        if record is None or record.project_id != project_id:
            return CommandResult(success=False, error="INVALID_SESSION")
        session_store.touch_activity(session_id)
        reader = OutputReader(record.session_dir)
        raw, err = reader.read(seq, stream, offset=offset, max_bytes=max_bytes)
        if err is not None:
            return CommandResult(success=False, error=err)
        assert raw is not None
        text = raw.decode("utf-8", errors="replace")
        return CommandResult(
            success=True,
            data={
                "text": text,
                "bytes_read": len(raw),
                "offset": offset,
                "encoding": "utf-8",
            },
        )
