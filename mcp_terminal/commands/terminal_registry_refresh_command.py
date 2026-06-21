"""
terminal_registry_refresh command for mcp_terminal.

Force-rescan watch anchors and rebuild the in-memory project registry.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.commands.terminal_registry_refresh_metadata import (
    get_terminal_registry_refresh_metadata,
)
from mcp_terminal.runtime_context import refresh_project_registry, registry_list_watch_layout


class TerminalRegistryRefreshCommand(Command):
    """MCP command: terminal_registry_refresh."""

    name: ClassVar[str] = "terminal_registry_refresh"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = (
        "Rescan watch anchor directories and rebuild the in-memory project registry."
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
        refreshed = refresh_project_registry()
        layout = registry_list_watch_layout()
        layout["refreshed"] = refreshed
        return CommandResult(success=True, data=layout)  # type: ignore[arg-type]

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_terminal_registry_refresh_metadata(cls)
