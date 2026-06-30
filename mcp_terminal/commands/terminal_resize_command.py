"""Resize an interactive sandbox PTY."""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.commands.terminal_interactive_metadata import (
    interactive_metadata,
    shell_param,
)
from mcp_terminal.services.interactive_shell import resize_shell


class TerminalResizeCommand(Command):
    name: ClassVar[str] = "terminal_resize"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = "Resize an interactive sandbox PTY."
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
                "cols": {"type": "integer", "minimum": 20, "maximum": 400},
                "rows": {"type": "integer", "minimum": 5, "maximum": 120},
            },
            "required": ["shell_id", "cols", "rows"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        shell_id = str(kwargs.get("shell_id", "")).strip()
        cols = max(20, min(400, int(kwargs.get("cols", 120))))
        rows = max(5, min(120, int(kwargs.get("rows", 30))))
        err = resize_shell(shell_id=shell_id, cols=cols, rows=rows)
        if err is not None:
            return CommandResult(success=False, error=err)
        return CommandResult(success=True, data={"shell_id": shell_id, "cols": cols, "rows": rows})

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return interactive_metadata(
            cls,
            detailed_description="Updates the PTY window size for a sandbox shell.",
            parameters={
                "shell_id": shell_param(True),
                "cols": {
                    "description": "PTY width.",
                    "type": "integer",
                    "required": True,
                    "examples": [120],
                },
                "rows": {
                    "description": "PTY height.",
                    "type": "integer",
                    "required": True,
                    "examples": [30],
                },
            },
            success_data={"shell_id": "Interactive shell id.", "cols": "Columns.", "rows": "Rows."},
            usage_examples=[
                {
                    "description": "Resize shell",
                    "command": {
                        "shell_id": "8772a086-688d-4198-a0c4-f03817cc0e6c:46ce9394-01ca-4440-9c03-c4a7466c4ec5",
                        "cols": 100,
                        "rows": 40,
                    },
                }
            ],
        )
