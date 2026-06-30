"""Write input to an interactive sandbox PTY."""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.commands.terminal_interactive_metadata import (
    interactive_metadata,
    shell_param,
)
from mcp_terminal.services.interactive_shell import send_shell


class TerminalSendCommand(Command):
    name: ClassVar[str] = "terminal_send"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = "Send keystrokes/input bytes to an interactive sandbox PTY."
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
                "data": {"type": "string", "description": "Text to write to the PTY."},
            },
            "required": ["shell_id", "data"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        shell_id = str(kwargs.get("shell_id", "")).strip()
        data = str(kwargs.get("data", ""))
        err = send_shell(shell_id=shell_id, data=data)
        if err is not None:
            return CommandResult(success=False, error=err)
        return CommandResult(
            success=True, data={"shell_id": shell_id, "bytes_written": len(data.encode("utf-8"))}
        )

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return interactive_metadata(
            cls,
            detailed_description="Writes text to a sandbox PTY opened by terminal_attach.",
            parameters={
                "shell_id": shell_param(True),
                "data": {
                    "description": "Text to write, including newlines or control sequences.",
                    "type": "string",
                    "required": True,
                    "examples": ["print(2 + 2)\n"],
                },
            },
            success_data={
                "shell_id": "Interactive shell id.",
                "bytes_written": "UTF-8 byte count.",
            },
            usage_examples=[
                {
                    "description": "Send a line to the shell",
                    "command": {
                        "shell_id": "8772a086-688d-4198-a0c4-f03817cc0e6c:46ce9394-01ca-4440-9c03-c4a7466c4ec5",
                        "data": "pwd\n",
                    },
                }
            ],
        )
