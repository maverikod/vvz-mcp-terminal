"""info command for mcp_terminal.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.commands.info_metadata import get_info_metadata
from mcp_terminal.commands.info_resources import (
    TERMINAL_INFO_DOCS,
    TERMINAL_INFO_GUIDE_VERSION,
    TERMINAL_INFO_LIFECYCLE,
    TERMINAL_INFO_MARKDOWN,
    TERMINAL_INFO_SUMMARY,
    registered_command_entries,
    terminal_package_info,
)


class InfoCommand(Command):
    """Return the full MCP Terminal guide."""

    name: ClassVar[str] = "info"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = (
        "Detailed guide: sandbox workflow, interactive PTY, host execution, "
        "package docs, and troubleshooting."
    )
    category: ClassVar[str] = "system"
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
            "description": "No parameters; returns the full MCP Terminal guide.",
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        if kwargs:
            return CommandResult(
                success=False,
                error="VALIDATION_ERROR",
                data={"field": sorted(kwargs)[0]},
            )
        return CommandResult(
            success=True,
            data={
                "guide_version": TERMINAL_INFO_GUIDE_VERSION,
                "package": terminal_package_info(),
                "summary": TERMINAL_INFO_SUMMARY,
                "markdown": TERMINAL_INFO_MARKDOWN,
                "lifecycle": TERMINAL_INFO_LIFECYCLE,
                "registered_commands": registered_command_entries(),
                "docs": TERMINAL_INFO_DOCS,
            },
        )

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_info_metadata(cls)
