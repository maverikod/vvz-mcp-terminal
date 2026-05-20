"""Extended metadata for ``terminal_list``."""

from __future__ import annotations

from typing import Any, Dict, Type

_EXAMPLE_PROJECT = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_EXAMPLE_SESSION = "46ce9394-01ca-4440-9c03-c4a7466c4ec5"


def get_terminal_list_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Returns a **summary list** of recent commands for one terminal session, "
            "ordered by **launch timestamp descending** (newest first). Each row includes "
            "``seq``, status, exit code, execution kind, and a display string for the "
            "command.\n\n"
            "This is a **read-only** navigation helper. Use ``terminal_get`` with a "
            "specific ``seq`` for full metadata (argv, cwd, output file names, job_id). "
            "Use ``terminal_get_status`` to poll queue and completion for a run in "
            "progress.\n\n"
            "Requires a valid ``project_id`` and ``session_id`` from "
            "``terminal_session_create``. Touching the session updates last-activity for "
            "TTL cleanup."
        ),
        "parameters": {
            "project_id": {
                "description": (
                    "Project UUID4. Must match the project used in "
                    "terminal_session_create."
                ),
                "type": "string",
                "required": True,
                "examples": [_EXAMPLE_PROJECT],
            },
            "session_id": {
                "description": "Session UUID4 from terminal_session_create.",
                "type": "string",
                "required": True,
                "examples": [_EXAMPLE_SESSION],
            },
            "limit": {
                "description": (
                    "Maximum number of history rows to return (newest first). "
                    "Schema default is 25; allowed range 1–200."
                ),
                "type": "integer",
                "required": False,
                "default": 25,
                "examples": [25, 50],
            },
        },
        "return_value": {
            "success": {
                "description": (
                    "Array of command summaries from ``history.jsonl``, newest first."
                ),
                "data": {
                    "items": (
                        "List of objects: seq, timestamp, status, exit_code, "
                        "execution_kind, command_display."
                    ),
                    "seq": "Session-local monotonic command number.",
                    "timestamp": "ISO-8601 launch time from history.",
                    "status": "Terminal command status (e.g. pending, completed).",
                    "exit_code": "Shell exit code when completed; may be null while pending.",
                    "execution_kind": "shell or argv as recorded for the run.",
                    "command_display": (
                        "Original shell command string, or space-joined argv when "
                        "command is empty."
                    ),
                },
                "example": {
                    "success": True,
                    "data": [
                        {
                            "seq": 2,
                            "timestamp": "2026-05-20T12:00:01Z",
                            "status": "completed",
                            "exit_code": 0,
                            "execution_kind": "argv",
                            "command_display": "pytest -q",
                        },
                        {
                            "seq": 1,
                            "timestamp": "2026-05-20T11:59:00Z",
                            "status": "completed",
                            "exit_code": 0,
                            "execution_kind": "shell",
                            "command_display": "ls -la",
                        },
                    ],
                },
            },
            "error": {
                "description": "Invalid identifiers or unknown session.",
                "code": "INVALID_SESSION",
                "message": "Stable error code string.",
                "details": "Optional field hint from validation.",
            },
        },
        "usage_examples": [
            {
                "description": "List last 25 commands (default limit)",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                },
                "explanation": (
                    "Returns newest-first summaries. Pick a seq and call terminal_get "
                    "for full detail."
                ),
            },
            {
                "description": "List up to 50 recent commands",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "limit": 50,
                },
                "explanation": "limit is capped at 200 by schema.",
            },
        ],
        "error_cases": {
            "INVALID_PROJECT_ID": {
                "description": "project_id is not a valid UUID4.",
                "message": "INVALID_PROJECT_ID",
                "solution": (
                    "Use a UUID4 from terminal_list_watch or terminal_session_create."
                ),
            },
            "INVALID_SESSION_ID": {
                "description": "session_id is not a valid UUID4.",
                "message": "INVALID_SESSION_ID",
                "solution": "Use the session_id returned by terminal_session_create.",
            },
            "INVALID_SESSION": {
                "description": "No session directory for (project_id, session_id).",
                "message": "INVALID_SESSION",
                "solution": "Call terminal_session_create before terminal_list.",
            },
        },
        "best_practices": [
            "Use terminal_list to discover recent seq values before terminal_get or terminal_tail.",
            "Default limit 25 is enough for interactive debugging; raise limit only when needed.",
            (
                "For completion polling of a specific run, use terminal_get_status "
                "rather than re-listing."
            ),
            "command_display is for display only; use terminal_get for argv and resolved_argv.",
        ],
    }
