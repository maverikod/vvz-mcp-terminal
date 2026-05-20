"""Extended metadata for ``terminal_sessions``."""

from __future__ import annotations

from typing import Any, Dict, Type

_EXAMPLE_PROJECT = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_EXAMPLE_SESSION = "46ce9394-01ca-4440-9c03-c4a7466c4ec5"


def get_terminal_sessions_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Returns **session summaries** for one project: every terminal session "
            "known to the in-memory ``SessionStore`` for that ``project_id``, up to "
            "``limit`` rows.\n\n"
            "This is a **read-only** project-scoped listing. It does not read command "
            "history or output files. Use ``terminal_list`` per session for recent "
            "commands, or ``terminal_session_create`` to open a new session.\n\n"
            "The project must resolve through the project registry (same as other "
            "project-scoped commands). Unknown ``project_id`` returns "
            "``PROJECT_NOT_FOUND``."
        ),
        "parameters": {
            "project_id": {
                "description": (
                    "Project UUID4. Use terminal_list_watch to discover valid "
                    "project_id values."
                ),
                "type": "string",
                "required": True,
                "examples": [_EXAMPLE_PROJECT],
            },
            "limit": {
                "description": (
                    "Maximum number of session summaries to return. Schema default "
                    "is 25; allowed range 1–500."
                ),
                "type": "integer",
                "required": False,
                "default": 25,
                "examples": [25, 100],
            },
        },
        "return_value": {
            "success": {
                "description": (
                    "Array of session summary objects for the project (truncated by limit)."
                ),
                "data": {
                    "session_id": "Session UUID4.",
                    "project_id": "Project UUID4 (echo of request).",
                    "created_at": "ISO-8601 session creation time.",
                    "last_activity_at": "ISO-8601 last touch (commands or reads).",
                    "status": "Session status string (e.g. idle).",
                    "workspace_write": (
                        "True when this session holds the project workspace write lock."
                    ),
                },
                "example": {
                    "success": True,
                    "data": [
                        {
                            "session_id": _EXAMPLE_SESSION,
                            "project_id": _EXAMPLE_PROJECT,
                            "created_at": "2026-05-20T10:00:00+00:00",
                            "last_activity_at": "2026-05-20T12:00:01+00:00",
                            "status": "idle",
                            "workspace_write": True,
                        },
                    ],
                },
            },
            "error": {
                "description": "Project not found in registry.",
                "code": "PROJECT_NOT_FOUND",
                "message": "PROJECT_NOT_FOUND",
                "details": "Optional registry resolution detail.",
            },
        },
        "usage_examples": [
            {
                "description": "List up to 25 sessions (default limit)",
                "command": {"project_id": _EXAMPLE_PROJECT},
                "explanation": (
                    "Returns in-memory sessions for the project. Use session_id with "
                    "terminal_list or terminal_session_create."
                ),
            },
            {
                "description": "List up to 100 sessions",
                "command": {"project_id": _EXAMPLE_PROJECT, "limit": 100},
                "explanation": "limit is capped at 500 by schema.",
            },
        ],
        "error_cases": {
            "PROJECT_NOT_FOUND": {
                "description": (
                    "project_id does not resolve to a known project directory."
                ),
                "message": "PROJECT_NOT_FOUND",
                "solution": (
                    "Call terminal_list_watch and retry with a registered project_id."
                ),
            },
        },
        "best_practices": [
            "Use terminal_sessions to see active sessions before terminal_delete.",
            "After terminal_delete, confirm removal with a second terminal_sessions call.",
            "workspace_write true means only one writer session per project is allowed.",
            "Sessions on disk but not loaded in SessionStore may not appear until touched.",
        ],
    }
