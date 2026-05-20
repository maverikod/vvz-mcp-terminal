"""Extended metadata for ``terminal_stat``."""

from __future__ import annotations

from typing import Any, Dict, Type

_EXAMPLE_PROJECT = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_EXAMPLE_SESSION = "46ce9394-01ca-4440-9c03-c4a7466c4ec5"


def get_terminal_stat_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Returns **output file metadata** (names and byte sizes) for one command "
            "``seq`` without reading file content. Files are "
            "``NNNNNN.stdout.log`` and ``NNNNNN.stderr.log`` under the session "
            "``.terminals`` directory.\n\n"
            "This is a **read-only** size probe. Missing log files report "
            "``stdout_bytes`` / ``stderr_bytes`` as 0 while still returning the "
            "expected file names.\n\n"
            "Use ``terminal_tail`` or ``terminal_read`` to fetch output bytes. "
            "Use ``terminal_get`` for full command history fields including the "
            "same file names.\n\n"
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
            "seq": {
                "description": (
                    "Session-local command sequence number from terminal_run, "
                    "terminal_run_host, or terminal_list."
                ),
                "type": "integer",
                "required": True,
                "examples": [1, 25],
            },
        },
        "return_value": {
            "success": {
                "description": "Output file names and byte sizes for the requested seq.",
                "data": {
                    "seq": "Echo of the requested sequence number.",
                    "stdout_file": "Relative stdout log file name.",
                    "stderr_file": "Relative stderr log file name.",
                    "stdout_bytes": "Size in bytes of stdout log (0 if missing).",
                    "stderr_bytes": "Size in bytes of stderr log (0 if missing).",
                },
                "example": {
                    "success": True,
                    "data": {
                        "seq": 1,
                        "stdout_file": "000001.stdout.log",
                        "stderr_file": "000001.stderr.log",
                        "stdout_bytes": 4096,
                        "stderr_bytes": 128,
                    },
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
                "description": "Check output sizes before reading seq 1",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "seq": 1,
                },
                "explanation": (
                    "Use stdout_bytes and stderr_bytes to decide between terminal_tail "
                    "and terminal_read paging."
                ),
            },
            {
                "description": "Verify logs exist after terminal_run completes",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "seq": 3,
                },
                "explanation": (
                    "Non-zero stdout_bytes confirms output was captured; zero may mean "
                    "the command produced no stdout yet or the file is absent."
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
                "solution": "Call terminal_session_create before terminal_stat.",
            },
        },
        "best_practices": [
            "Call terminal_stat before terminal_read on large logs to choose offset/max_bytes.",
            "Combine with terminal_get_status to know when sizes stop growing.",
            "Zero byte counts are normal for commands that write only to one stream.",
            "File names match those returned by terminal_get for the same seq.",
        ],
    }
