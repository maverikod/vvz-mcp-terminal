"""
terminal_list_watch command for mcp_terminal (C-014).

Returns configured watch anchor directories and projects discovered under each.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.commands.terminal_list_watch_metadata import (
    get_terminal_list_watch_metadata,
)
from mcp_terminal.runtime_context import registry_list_watch_layout


class TerminalListWatchCommand(Command):
    """MCP command: terminal_list_watch."""

    name: ClassVar[str] = "terminal_list_watch"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = (
        "List watch anchor directories and projects (projectid) found under each. "
        "Read-only snapshot of the in-memory project registry."
    )
    category: ClassVar[str] = "custom"
    author: ClassVar[str] = "Vasiliy Zdanovskiy"
    email: ClassVar[str] = "vasilyvz@gmail.com"
    result_class: ClassVar[Type[CommandResult]] = CommandResult

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        layout = registry_list_watch_layout()
        return CommandResult(success=True, data=layout)  # type: ignore[arg-type]

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_terminal_list_watch_metadata(cls)
