"""Read output from an interactive sandbox PTY."""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.commands.terminal_interactive_metadata import (
    interactive_metadata,
    shell_param,
)
from mcp_terminal.services.interactive_shell import read_shell


class TerminalReadShellCommand(Command):
    name: ClassVar[str] = "terminal_read_shell"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = "Read incremental output from an interactive sandbox PTY."
    category: ClassVar[str] = "custom"
    author: ClassVar[str] = "Vasiliy Zdanovskiy"
    email: ClassVar[str] = "vasilyvz@gmail.com"
    result_class: ClassVar[Type[CommandResult]] = CommandResult

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "shell_id": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0},
                "max_bytes": {
                    "type": "integer",
                    "default": 65536,
                    "minimum": 1,
                    "maximum": 1048576,
                },
            },
            "required": ["shell_id"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        shell_id = str(kwargs.get("shell_id", "")).strip()
        offset = int(kwargs["offset"]) if "offset" in kwargs else None
        max_bytes = max(1, min(1048576, int(kwargs.get("max_bytes", 65536))))
        data, err = read_shell(shell_id=shell_id, offset=offset, max_bytes=max_bytes)
        if err is not None or data is None:
            return CommandResult(success=False, error=err or "READ_FAILED")
        return CommandResult(success=True, data=data)

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return interactive_metadata(
            cls,
            detailed_description="Reads buffered PTY output from a sandbox shell by byte offset.",
            parameters={
                "shell_id": shell_param(True),
                "offset": {
                    "description": "Byte offset to read from. Omit to read from retained start.",
                    "type": "integer",
                    "required": False,
                    "examples": [0],
                },
                "max_bytes": {
                    "description": "Maximum bytes to return.",
                    "type": "integer",
                    "required": False,
                    "default": 65536,
                    "examples": [65536],
                },
            },
            success_data={
                "data": "Decoded PTY output chunk.",
                "next_offset": "Offset for the next read.",
                "running": "Whether the PTY process is still running.",
            },
            usage_examples=[
                {
                    "description": "Read fresh shell output",
                    "command": {
                        "shell_id": "8772a086-688d-4198-a0c4-f03817cc0e6c:46ce9394-01ca-4440-9c03-c4a7466c4ec5",
                        "offset": 0,
                    },
                }
            ],
        )
