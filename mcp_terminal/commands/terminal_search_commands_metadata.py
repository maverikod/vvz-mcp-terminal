"""Extended metadata for ``terminal_search_commands``."""

from __future__ import annotations

from typing import Any, Dict, Type

_EXAMPLE_PROJECT = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_EXAMPLE_SESSION = "46ce9394-01ca-4440-9c03-c4a7466c4ec5"


def get_terminal_search_commands_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Searches **command history metadata** in a session for entries whose "
            "display command text or status matches a **regex pattern**. Data comes "
            "from ``history.jsonl`` — not from stdout/stderr output files.\n\n"
            "Matching is applied to the command display string (original shell command "
            "or space-joined argv) and to the recorded ``status`` field. Results are "
            "returned in history order until ``limit`` matches are collected.\n\n"
            "This is a **read-only** navigation helper. For regex search inside "
            "command output, use ``terminal_search_output``. For full fields on one "
            "``seq``, use ``terminal_get``.\n\n"
            "Requires a valid ``project_id`` and ``session_id``. Touching the session "
            "updates last-activity for TTL cleanup."
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
            "pattern": {
                "description": (
                    "Regular expression applied to command display text and status. "
                    "Invalid regex syntax returns INVALID_PATTERN."
                ),
                "type": "string",
                "required": True,
                "examples": ["pytest", "failed|error"],
            },
            "limit": {
                "description": (
                    "Maximum number of matching history rows to return. Schema default "
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
                "description": "Array of matching command summaries from history.",
                "data": {
                    "items": (
                        "List of objects: seq, timestamp, status, exit_code, "
                        "command_display."
                    ),
                    "seq": "Session-local command sequence number.",
                    "timestamp": "ISO-8601 launch time from history.",
                    "status": "Terminal command status at match time.",
                    "exit_code": "Shell exit code when completed; may be null while pending.",
                    "command_display": (
                        "Original shell command string, or space-joined argv."
                    ),
                },
                "example": {
                    "success": True,
                    "data": [
                        {
                            "seq": 2,
                            "timestamp": "2026-05-20T12:05:00Z",
                            "status": "completed",
                            "exit_code": 0,
                            "command_display": "pytest tests/test_foo.py -q",
                        },
                    ],
                },
            },
            "error": {
                "description": "Invalid identifiers, unknown session, or bad regex.",
                "code": "INVALID_PATTERN",
                "message": "Stable error code string.",
                "details": "Regex compile error detail when pattern is invalid.",
            },
        },
        "usage_examples": [
            {
                "description": "Find pytest runs in session history",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "pattern": "pytest",
                },
                "explanation": (
                    "Returns up to 25 matches by default. Use terminal_get on a seq "
                    "for full metadata."
                ),
            },
            {
                "description": "Find failed commands with a higher limit",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "pattern": "failed",
                    "limit": 50,
                },
                "explanation": (
                    "Pattern matches status text as well as command display strings."
                ),
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
                "solution": (
                    "Call terminal_session_create before terminal_search_commands."
                ),
            },
            "INVALID_PATTERN": {
                "description": "pattern is not a valid regular expression.",
                "message": "INVALID_PATTERN: …",
                "solution": "Fix the regex syntax and retry.",
            },
        },
        "best_practices": [
            "Use terminal_list for unfiltered recent history; search when filtering by text.",
            "Anchor patterns (^/$) when you need exact command matches.",
            "Follow up with terminal_get on a matched seq for argv, cwd, and output files.",
            "Search output logs with terminal_search_output, not this command.",
        ],
    }
