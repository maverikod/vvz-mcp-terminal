"""Extended metadata for ``terminal_search_output``."""

from __future__ import annotations

from typing import Any, Dict, Type

from mcp_terminal.services.output_reader import DEFAULT_MAX_MATCHES

_EXAMPLE_PROJECT = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_EXAMPLE_SESSION = "46ce9394-01ca-4440-9c03-c4a7466c4ec5"


def get_terminal_search_output_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Searches **one command output file** (``stdout`` or ``stderr``) for "
            "lines matching a **regex pattern**, up to ``max_matches`` hits. Files "
            "are ``NNNNNN.stdout.log`` / ``NNNNNN.stderr.log`` under the session "
            "``.terminals`` directory.\n\n"
            "Matching is **line-wise**: each line is tested independently. If the "
            "log file does not exist yet, the command succeeds with an empty "
            "``matches`` list and ``count`` 0.\n\n"
            "This is a **read-only** output accessor. For command history search "
            "by command text or status, use ``terminal_search_commands``. For the "
            "last N lines without regex, use ``terminal_tail``.\n\n"
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
                "description": "Which output stream file to search.",
                "type": "string",
                "required": True,
                "enum": ["stdout", "stderr"],
                "examples": ["stdout", "stderr"],
            },
            "pattern": {
                "description": (
                    "Regular expression applied line-wise to the stream file. "
                    "Invalid regex syntax returns INVALID_PATTERN."
                ),
                "type": "string",
                "required": True,
                "examples": ["ERROR", "FAILED|AssertionError"],
            },
            "max_matches": {
                "description": (
                    "Maximum matching lines to return. Schema default is "
                    f"{DEFAULT_MAX_MATCHES}; allowed range 1–5000."
                ),
                "type": "integer",
                "required": False,
                "default": DEFAULT_MAX_MATCHES,
                "examples": [10, DEFAULT_MAX_MATCHES],
            },
        },
        "return_value": {
            "success": {
                "description": "Matching lines from the requested output file.",
                "data": {
                    "matches": (
                        "List of objects: seq, stream, line_number, text (full line)."
                    ),
                    "count": "Number of matches returned (≤ max_matches).",
                    "seq": "Echo of the requested sequence number.",
                    "stream": "Echo of the searched stream.",
                    "line_number": "1-based line number in the log file.",
                    "text": "Full matched line text.",
                },
                "example": {
                    "success": True,
                    "data": {
                        "matches": [
                            {
                                "seq": 1,
                                "stream": "stderr",
                                "line_number": 42,
                                "text": "ERROR: module not found",
                            },
                        ],
                        "count": 1,
                    },
                },
            },
            "error": {
                "description": (
                    "Invalid identifiers, unknown session, invalid stream, or bad regex."
                ),
                "code": "INVALID_PATTERN",
                "message": "Stable error code string.",
                "details": "Regex compile error detail when pattern is invalid.",
            },
        },
        "usage_examples": [
            {
                "description": "Find ERROR lines in stderr for seq 1",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "seq": 1,
                    "stream": "stderr",
                    "pattern": "ERROR",
                },
                "explanation": (
                    "Uses default max_matches=50. Increase max_matches for noisy logs."
                ),
            },
            {
                "description": "Search stdout for test failures with a cap",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "seq": 2,
                    "stream": "stdout",
                    "pattern": "FAILED",
                    "max_matches": 10,
                },
                "explanation": (
                    "line_number helps correlate hits with terminal_tail context."
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
                    "Call terminal_session_create before terminal_search_output."
                ),
            },
            "INVALID_STREAM": {
                "description": "stream is not stdout or stderr.",
                "message": "INVALID_STREAM",
                "solution": "Use stream stdout or stderr as defined in get_schema().",
            },
            "INVALID_PATTERN": {
                "description": "pattern is not a valid regular expression.",
                "message": "INVALID_PATTERN: …",
                "solution": "Fix the regex syntax and retry.",
            },
        },
        "best_practices": [
            "Discover seq with terminal_list, then search the relevant stream.",
            "Use terminal_stat to gauge log size before searching very large files.",
            "Prefer terminal_tail when you only need recent lines, not full-file regex.",
            "Search history metadata with terminal_search_commands, not this command.",
        ],
    }
