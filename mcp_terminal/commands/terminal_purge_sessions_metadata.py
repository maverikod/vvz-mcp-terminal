"""Extended metadata for ``terminal_purge_sessions``."""

from __future__ import annotations

from typing import Any, Dict, Type


def get_terminal_purge_sessions_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Global purge of **all** ``.terminals/<session_id>/`` trees under project watch "
            "anchors (same scope as ``termgr purge-sessions``). Optionally kills sandbox "
            "Docker containers and removes ``.mcp_terminal/`` runtime dirs.\n\n"
            "**Gated by config:** requires ``terminal.admin.allow_purge_sessions: true`` "
            "in the active term server config. When false, the command returns "
            "``PURGE_SESSIONS_DISABLED`` (same gate as the CLI).\n\n"
            "**Safety:** this is destructive across every watched project root. Prefer "
            "``terminal_delete`` for a single session. Use ``dry_run: true`` first.\n\n"
            "**Note:** in-memory ``SessionStore`` entries are not cleared by this command; "
            "restart ``termgr`` if you need a clean process state after a non-dry purge."
        ),
        "parameters": {
            "dry_run": {
                "description": "Preview counts without deleting or killing containers.",
                "type": "boolean",
                "required": False,
                "default": False,
            },
            "kill_docker": {
                "description": "Remove matching terminal sandbox Docker containers.",
                "type": "boolean",
                "required": False,
                "default": True,
            },
            "remove_runtime": {
                "description": "Also delete each project's ``.mcp_terminal/`` directory.",
                "type": "boolean",
                "required": False,
                "default": False,
            },
        },
        "return_value": {
            "success": {
                "description": "Purge completed (dry_run or applied).",
                "data": {
                    "containers_killed": "Docker containers removed (or counted in dry_run).",
                    "session_dirs_removed": "Session directories removed or counted.",
                    "empty_terminals_trees_removed": "Empty .terminals roots removed.",
                    "runtime_dirs_removed": ".mcp_terminal trees removed when requested.",
                    "errors": "List of non-fatal error strings.",
                },
                "example": {
                    "success": True,
                    "data": {
                        "containers_killed": 0,
                        "session_dirs_removed": 2,
                        "empty_terminals_trees_removed": 1,
                        "runtime_dirs_removed": 0,
                        "errors": [],
                    },
                },
            },
            "error": {
                "description": "Purge disabled or validation failure.",
                "code": "PURGE_SESSIONS_DISABLED",
                "message": "Stable error code.",
                "details": "Optional context.",
            },
        },
        "usage_examples": [
            {
                "description": "Preview purge impact",
                "command": {"dry_run": True, "kill_docker": True},
                "explanation": "Counts session dirs and containers without applying changes.",
            },
        ],
        "error_cases": {
            "PURGE_SESSIONS_DISABLED": {
                "description": "``terminal.admin.allow_purge_sessions`` is not true.",
                "message": "PURGE_SESSIONS_DISABLED",
                "solution": (
                    "Set terminal.admin.allow_purge_sessions to true in term_server.json "
                    "and restart the server; use only on trusted hosts."
                ),
            },
        },
        "best_practices": [
            "Run with dry_run true before a real purge.",
            "Use terminal_delete for normal session teardown instead of global purge.",
            "Keep ``allow_purge_sessions`` false in production if global purge must not be used.",
        ],
    }
