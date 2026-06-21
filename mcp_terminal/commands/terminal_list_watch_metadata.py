"""Extended metadata for ``terminal_list_watch``."""

from __future__ import annotations

from typing import Any, Dict, Type


def get_terminal_list_watch_metadata(cls: Type[Any]) -> Dict[str, Any]:
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
            "indicate duplicate ``project_id`` conflicts.\n\n"
            "By default rescans watch anchors from disk before returning the layout "
            "(``rescan: true``). Set ``rescan: false`` for a fast in-memory snapshot "
            "only. Use enabled project_id values for ``terminal_session_create`` and "
            "other project-scoped commands."
        ),
        "parameters": {
            "rescan": {
                "description": (
                    "Rescan watch anchors from disk before building the response "
                    "(default true)."
                ),
                "type": "boolean",
                "required": False,
                "default": True,
            },
        },
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
                "description": "This command always returns success when the registry is initialised.",
                "code": "(none)",
                "message": "Read-only snapshot; no rejection path in normal operation.",
                "details": "Registry is rebuilt on each call when rescan is true.",
            },
        },
        "usage_examples": [
            {
                "description": "List anchors and projects (rescan from disk)",
                "command": {},
                "explanation": "Default rescan=true; returns the current on-disk layout.",
            },
            {
                "description": "In-memory snapshot without rescan",
                "command": {"rescan": False},
                "explanation": "Fast snapshot; may miss projectid files added after last refresh.",
            },
        ],
        "error_cases": {},
        "best_practices": [
            (
                "Always use this command (or ``registry_list_watch_layout`` in code); "
                "do not call ``list_watch_layout`` on a bare ``get_project_registry()`` "
                "reference — it is not synchronized with background registry refresh."
            ),
            "Use after changing watch_dirs or when debugging empty project_id resolution.",
            "Treat paths as host-side diagnostics, not workspace-relative paths.",
            "Skip project rows with disabled: true when choosing a project_id.",
        ],
    }
