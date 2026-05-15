"""
terminal_list_watch command for mcp_terminal (C-014).

Returns configured watch anchor directories and projects discovered under each.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

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
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "Returns one row per configured watch anchor (merged from "
                "``watch_dirs.directories`` and Code Analysis watch paths when enabled). "
                "Under each anchor, lists projects discovered as immediate subdirectories "
                "containing a valid ``projectid`` file. Entries with ``disabled: true`` "
                "indicate duplicate ``project_id`` conflicts."
            ),
            "parameters": {},
            "return_value": {
                "success": {
                    "description": "Snapshot returned.",
                    "data": {
                        "watch_directories": "Array of { directory, projects[] }.",
                        "totals": (
                            "watch_directory_count, registry_entry_count, "
                            "enabled_project_count."
                        ),
                    },
                    "example": {
                        "success": True,
                        "data": {
                            "watch_directories": [
                                {
                                    "directory": "/data/workspaces",
                                    "projects": [
                                        {
                                            "project_id": "550e8400-e29b-41d4-a716-446655440000",
                                            "description": "Example",
                                            "project_dir": "/data/workspaces/example",
                                            "disabled": False,
                                            "conflict_reason": None,
                                        }
                                    ],
                                }
                            ],
                            "totals": {
                                "watch_directory_count": 1,
                                "registry_entry_count": 1,
                                "enabled_project_count": 1,
                            },
                        },
                    },
                },
                "error": {
                    "description": "Registry not configured (should not occur after server start).",
                    "code": "INTERNAL_ERROR",
                    "message": "…",
                    "details": "…",
                },
            },
            "usage_examples": [
                {
                    "description": "List anchors and projects",
                    "command": {},
                    "explanation": "No parameters; returns the current discovery layout.",
                }
            ],
            "error_cases": {
                "INTERNAL_ERROR": {
                    "description": "ProjectRegistry was not initialised.",
                    "message": "RuntimeError from runtime_context",
                    "solution": "Restart term_server with a valid config.",
                },
            },
            "best_practices": [
                "Always use this command (or ``registry_list_watch_layout`` in code); "
                "do not call ``list_watch_layout`` on a bare ``get_project_registry()`` "
                "reference — it is not synchronized with background registry refresh.",
                "Use after changing watch_dirs or when debugging empty project_id resolution.",
                "Treat paths as host-side diagnostics, not workspace-relative paths.",
            ],
        }
