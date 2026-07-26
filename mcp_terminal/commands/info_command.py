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
    DEFAULT_INFO_PAGE_SIZE,
    MAX_INFO_PAGE_SIZE,
    TERMINAL_INFO_GUIDE_VERSION,
    TERMINAL_INFO_LIFECYCLE,
    TERMINAL_INFO_MARKDOWN,
    TERMINAL_INFO_SUMMARY,
    paginate_terminal_info,
    registered_command_entries,
    terminal_package_info,
    terminal_info_total_pages,
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
            "properties": {
                "page": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 1,
                    "description": "1-based guide page number.",
                },
                "page_size": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_INFO_PAGE_SIZE,
                    "default": DEFAULT_INFO_PAGE_SIZE,
                    "description": "Number of top-level guide sections per page.",
                },
            },
            "required": [],
            "additionalProperties": False,
            "description": "Returns one paginated slice of the MCP Terminal guide.",
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        allowed = {"page", "page_size"}
        unknown = sorted(set(kwargs) - allowed)
        if unknown:
            return CommandResult(
                success=False,
                error="VALIDATION_ERROR",
                data={"field": unknown[0]},
            )
        try:
            page = int(kwargs.get("page", 1))
            page_size = int(kwargs.get("page_size", DEFAULT_INFO_PAGE_SIZE))
        except (TypeError, ValueError):
            return CommandResult(
                success=False,
                error="VALIDATION_ERROR",
                data={"field": "page"},
            )
        if page < 1:
            return CommandResult(
                success=False,
                error="VALIDATION_ERROR",
                data={"field": "page"},
            )
        if page_size < 1 or page_size > MAX_INFO_PAGE_SIZE:
            return CommandResult(
                success=False,
                error="VALIDATION_ERROR",
                data={"field": "page_size"},
            )
        try:
            info_page = paginate_terminal_info(page=page, page_size=page_size)
        except ValueError:
            return CommandResult(
                success=False,
                error="PAGE_OUT_OF_RANGE",
                data={
                    "page": page,
                    "page_size": page_size,
                    "total_pages": terminal_info_total_pages(page_size),
                },
            )
        return CommandResult(
            success=True,
            data={
                "guide_version": TERMINAL_INFO_GUIDE_VERSION,
                "package": terminal_package_info(),
                "summary": TERMINAL_INFO_SUMMARY,
                "markdown": info_page.markdown,
                "lifecycle": TERMINAL_INFO_LIFECYCLE,
                "registered_commands": registered_command_entries(),
                "docs": TERMINAL_INFO_DOCS,
                "sections": [
                    {
                        "title": section.title,
                        "markdown": section.markdown,
                    }
                    for section in info_page.sections
                ],
                "pagination": {
                    "page": info_page.page,
                    "page_size": info_page.page_size,
                    "total_pages": info_page.total_pages,
                    "total_sections": info_page.total_sections,
                    "has_prev": info_page.has_prev,
                    "has_next": info_page.has_next,
                },
                "full_markdown": TERMINAL_INFO_MARKDOWN,
            },
        )

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_info_metadata(cls)
