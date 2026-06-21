"""Extended metadata for ``terminal_registry_refresh``."""

from __future__ import annotations

from typing import Any, Dict, Type


def get_terminal_registry_refresh_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Re-reads all configured watch anchor directories (from ``watch_dirs`` "
            "and Code Analysis when enabled), rebuilds the in-memory project "
            "registry from ``projectid`` files on disk, and returns the updated "
            "layout.\n\n"
            "Use after CA database rebuilds or when ``projectid`` files change "
            "without restarting the terminal process. Project-scoped commands "
            "also trigger an automatic rescan on ``PROJECT_NOT_FOUND`` before "
            "returning that error."
        ),
        "parameters": {},
        "return_value": {
            "success": {
                "description": "Registry rescan completed (or skipped if startup incomplete).",
                "data": {
                    "refreshed": (
                        "True when the registry was rebuilt from disk; False when "
                        "refresh sources were not configured."
                    ),
                    "watch_directories": "Same shape as ``terminal_list_watch``.",
                    "totals": "Same shape as ``terminal_list_watch``.",
                },
                "example": {
                    "success": True,
                    "data": {
                        "refreshed": True,
                        "watch_directories": [],
                        "totals": {
                            "watch_directory_count": 0,
                            "registry_entry_count": 0,
                            "enabled_project_count": 0,
                        },
                    },
                },
            },
            "error": {
                "description": "This command always returns success when the registry is initialised.",
                "code": "(none)",
                "message": "Read-only rescan; no rejection path in normal operation.",
                "details": "Verify ``refreshed`` is true after server startup.",
            },
        },
        "usage_examples": [
            {
                "description": "Force registry rescan after CA project rebuild",
                "command": {},
                "explanation": (
                    "No parameters; rescans anchors and returns the current "
                    "project layout."
                ),
            },
        ],
        "error_cases": {},
        "best_practices": [
            "Call after CA recreates ``projectid`` files under watch anchors.",
            "Prefer ``terminal_list_watch`` with default ``rescan: true`` for read-only checks.",
            "If ``refreshed`` is false, the server may still be starting — retry shortly.",
        ],
    }
