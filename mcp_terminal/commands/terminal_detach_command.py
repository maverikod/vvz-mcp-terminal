"""Detach an interactive sandbox PTY."""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.commands.terminal_interactive_metadata import (
    interactive_metadata,
    shell_param,
)
from mcp_terminal.services.interactive_shell import close_shell


class TerminalDetachCommand(Command):
    name: ClassVar[str] = "terminal_detach"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = "Detach and stop an interactive sandbox PTY."
    category: ClassVar[str] = "custom"
    author: ClassVar[str] = "Vasiliy Zdanovskiy"
    email: ClassVar[str] = "vasilyvz@gmail.com"
    result_class: ClassVar[Type[CommandResult]] = CommandResult

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"shell_id": {"type": "string"}},
            "required": ["shell_id"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        shell_id = str(kwargs.get("shell_id", "")).strip()
        err = close_shell(shell_id=shell_id)
        if err is not None:
            return CommandResult(success=False, error=err)
        return CommandResult(success=True, data={"shell_id": shell_id, "detached": True})

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return interactive_metadata(
            cls,
            detailed_description="Stops the server-managed PTY process for a sandbox shell.",
            parameters={"shell_id": shell_param(True)},
            success_data={"shell_id": "Interactive shell id.", "detached": "True when closed."},
            usage_examples=[
                {
                    "description": "Detach shell",
                    "command": {
                        "shell_id": "8772a086-688d-4198-a0c4-f03817cc0e6c:46ce9394-01ca-4440-9c03-c4a7466c4ec5"
                    },
                }
            ],
        )
