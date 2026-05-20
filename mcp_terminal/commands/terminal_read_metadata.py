"""Extended metadata for ``terminal_read``."""

from __future__ import annotations

from typing import Any, Dict, Type

from mcp_terminal.services.output_reader import DEFAULT_MAX_BYTES

_EXAMPLE_PROJECT = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_EXAMPLE_SESSION = "46ce9394-01ca-4440-9c03-c4a7466c4ec5"


def get_terminal_read_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Reads a **byte slice** from one command output file (``stdout`` or "
            "``stderr``) for a session-local ``seq``. Files are named "
            "``NNNNNN.stdout.log`` / ``NNNNNN.stderr.log`` under the session "
            "``.terminals`` directory.\n\n"
            "This is a **read-only** output accessor. Use ``offset`` and "
            "``max_bytes`` to page through large logs. Text is returned as UTF-8 "
            "with replacement for invalid bytes. If the log file does not exist "
            "yet, the command succeeds with empty ``text`` and ``bytes_read`` 0.\n\n"
            "For line-oriented tailing, use ``terminal_tail``. For regex search "
            "across output, use ``terminal_search_output``. For command metadata "
            "(argv, status, file names), use ``terminal_get``.\n\n"
            "Requires a valid ``project_id`` and ``session_id``. Touching the "
            "session updates last-activity for TTL cleanup."
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
                "description": "Which output stream file to read.",
                "type": "string",
                "required": True,
                "enum": ["stdout", "stderr"],
                "examples": ["stdout", "stderr"],
            },
            "offset": {
                "description": (
                    "Byte offset into the stream file (0-based). Schema default "
                    "is 0; must be non-negative."
                ),
                "type": "integer",
                "required": False,
                "default": 0,
                "examples": [0, 65536],
            },
            "max_bytes": {
                "description": (
                    "Maximum bytes to read from the file starting at offset. "
                    f"Schema default is {DEFAULT_MAX_BYTES}; allowed range 1–1048576."
                ),
                "type": "integer",
                "required": False,
                "default": DEFAULT_MAX_BYTES,
                "examples": [4096, DEFAULT_MAX_BYTES],
            },
        },
        "return_value": {
            "success": {
                "description": "UTF-8 text slice from the requested output file.",
                "data": {
                    "text": "Decoded output bytes (invalid UTF-8 replaced).",
                    "bytes_read": "Number of raw bytes read (may be less than max_bytes).",
                    "offset": "Echo of the requested byte offset.",
                    "encoding": 'Always "utf-8" on success.',
                },
                "example": {
                    "success": True,
                    "data": {
                        "text": "============================= test session starts ===\n",
                        "bytes_read": 78,
                        "offset": 0,
                        "encoding": "utf-8",
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
                "description": "Read first chunk of stdout for seq 1",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "seq": 1,
                    "stream": "stdout",
                },
                "explanation": (
                    "Uses default offset 0 and max_bytes 65536. Page with offset += "
                    "bytes_read on subsequent calls."
                ),
            },
            {
                "description": "Read stderr from byte offset 1024",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "seq": 2,
                    "stream": "stderr",
                    "offset": 1024,
                    "max_bytes": 8192,
                },
                "explanation": "Smaller max_bytes reduces payload size for agents.",
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
                "solution": "Call terminal_session_create before terminal_read.",
            },
            "INVALID_STREAM": {
                "description": "stream is not stdout or stderr.",
                "message": "INVALID_STREAM",
                "solution": "Use stream stdout or stderr as defined in get_schema().",
            },
        },
        "best_practices": [
            "Discover seq with terminal_list, then read stdout/stderr for that seq.",
            "Use terminal_tail for the last N lines instead of large offset paging.",
            "Poll completion with terminal_get_status before reading a still-growing log.",
            "Increase max_bytes only when needed; default 65536 is enough for most chunks.",
        ],
    }
