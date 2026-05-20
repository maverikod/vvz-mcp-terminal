"""Extended metadata for ``terminal_tail``."""

from __future__ import annotations

from typing import Any, Dict, Type

from mcp_terminal.services.output_reader import DEFAULT_TAIL_LINES

_EXAMPLE_PROJECT = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_EXAMPLE_SESSION = "46ce9394-01ca-4440-9c03-c4a7466c4ec5"


def get_terminal_tail_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Returns the **last N lines** from one command output file (``stdout`` or "
            "``stderr``) for a session-local ``seq``. Files are named "
            "``NNNNNN.stdout.log`` / ``NNNNNN.stderr.log`` under the session "
            "``.terminals`` directory.\n\n"
            "This is a **read-only** line-oriented accessor. Use ``lines`` to cap "
            "payload size. If the log file does not exist yet, the command succeeds "
            "with an empty ``lines`` list and ``count`` 0.\n\n"
            "For byte-offset paging through large logs, use ``terminal_read``. For "
            "regex search within output, use ``terminal_search_output``. For command "
            "metadata and output file names, use ``terminal_get``.\n\n"
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
            "stream": {
                "description": "Which output stream file to tail.",
                "type": "string",
                "required": True,
                "enum": ["stdout", "stderr"],
                "examples": ["stdout", "stderr"],
            },
            "lines": {
                "description": (
                    "Number of trailing lines to return. Schema default is "
                    f"{DEFAULT_TAIL_LINES}; allowed range 1–10000."
                ),
                "type": "integer",
                "required": False,
                "default": DEFAULT_TAIL_LINES,
                "examples": [50, DEFAULT_TAIL_LINES],
            },
        },
        "return_value": {
            "success": {
                "description": "Trailing lines from the requested output file.",
                "data": {
                    "lines": "List of text lines (no trailing newline per element).",
                    "count": "Number of lines returned (may be less than lines requested).",
                },
                "example": {
                    "success": True,
                    "data": {
                        "lines": [
                            "=========================== test session starts ===",
                            "collected 3 items",
                            "...",
                            "============================== 3 passed in 0.12s ==",
                        ],
                        "count": 4,
                    },
                },
            },
            "error": {
                "description": "Invalid identifiers, unknown session, or invalid stream.",
                "code": "INVALID_SESSION",
                "message": "Stable error code string.",
                "details": "Optional field hint from validation.",
            },
        },
        "usage_examples": [
            {
                "description": "Tail last 100 lines of stdout for seq 1",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "seq": 1,
                    "stream": "stdout",
                },
                "explanation": (
                    "Uses default lines=100. Poll terminal_get_status while a run is "
                    "active, then tail again for fresh output."
                ),
            },
            {
                "description": "Tail last 20 stderr lines for seq 2",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "seq": 2,
                    "stream": "stderr",
                    "lines": 20,
                },
                "explanation": "Smaller lines value reduces payload for agents.",
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
                "solution": "Call terminal_session_create before terminal_tail.",
            },
            "INVALID_STREAM": {
                "description": "stream is not stdout or stderr.",
                "message": "INVALID_STREAM",
                "solution": "Use stream stdout or stderr as defined in get_schema().",
            },
        },
        "best_practices": [
            "Discover seq with terminal_list, then tail stdout or stderr for that seq.",
            "Use terminal_stat first to check file sizes before requesting many lines.",
            "Poll terminal_get_status before tailing output from a still-running command.",
            "Use terminal_search_output when you need regex matches instead of raw tail.",
        ],
    }
