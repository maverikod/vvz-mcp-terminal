"""Input schema for ``terminal_purge_sessions``."""

from __future__ import annotations

from typing import Any, Dict


def get_terminal_purge_sessions_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Preview only: count removable session dirs and containers without "
                    "deleting or killing."
                ),
            },
            "kill_docker": {
                "type": "boolean",
                "default": True,
                "description": (
                    "When true, remove terminal sandbox Docker containers "
                    "(mcp-term-*, ghcr.io/mcp-terminal/*, …)."
                ),
            },
            "remove_runtime": {
                "type": "boolean",
                "default": False,
                "description": (
                    "When true, also remove each project's ``.mcp_terminal/`` runtime build "
                    "directory next to ``.terminals``."
                ),
            },
        },
        "required": [],
        "additionalProperties": False,
    }
