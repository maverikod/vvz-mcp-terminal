"""Extended metadata for ``terminal_kill``."""

from __future__ import annotations

from typing import Any, Dict, Type

_EXAMPLE_PROJECT = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_EXAMPLE_SESSION = "46ce9394-01ca-4440-9c03-c4a7466c4ec5"


def get_terminal_kill_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Sends **SIGKILL** to the in-process ``docker run`` client subprocess for a "
            "session-local command seq while its history status is still **pending**. "
            "This is the same force-stop semantics as ``kill -9`` on POSIX "
            "(``subprocess.Popen.kill``).\n\n"
            "Only applies to sandbox runs started via ``terminal_run`` where the adapter "
            "still holds the subprocess handle. After the process exits, status becomes "
            "completed or failed and this command returns ``NOT_RUNNING``.\n\n"
            "Poll ``terminal_get_status`` afterward; ``exit_code`` may reflect signal "
            "termination. Does not stop the session container itself — use "
            "``terminal_delete`` for session teardown."
        ),
        "parameters": {
            "project_id": {
                "description": (
                    "Project UUID4. Must match the session and registry entry used for "
                    "``terminal_run``."
                ),
                "type": "string",
                "required": True,
                "examples": [_EXAMPLE_PROJECT],
            },
            "session_id": {
                "description": "Session UUID4 from ``terminal_session_create``.",
                "type": "string",
                "required": True,
                "examples": [_EXAMPLE_SESSION],
            },
            "seq": {
                "description": (
                    "Session-local command sequence number to kill (from ``terminal_run`` "
                    "response)."
                ),
                "type": "integer",
                "required": True,
                "examples": [1],
            },
        },
        "return_value": {
            "success": {
                "description": "SIGKILL was delivered to the registered subprocess.",
                "data": {
                    "session_id": "Echo.",
                    "seq": "Echo.",
                    "killed": "Always true on success.",
                    "signal": "Always SIGKILL.",
                },
                "example": {
                    "success": True,
                    "data": {
                        "session_id": _EXAMPLE_SESSION,
                        "seq": 1,
                        "killed": True,
                        "signal": "SIGKILL",
                    },
                },
            },
            "error": {
                "description": "Kill not applied or validation failed.",
                "code": "NOT_RUNNING",
                "message": "…",
                "details": "Optional detail for KILL_NOT_APPLIED.",
            },
        },
        "usage_examples": [
            {
                "description": "Force-stop a hung sandbox run",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "seq": 1,
                },
                "explanation": (
                    "Use when terminal_get_status shows pending and the command will not "
                    "finish. Poll terminal_get_status after kill."
                ),
            },
        ],
        "error_cases": {
            "INVALID_PROJECT_ID": {
                "description": "project_id is not a UUID4.",
                "solution": "Use a UUID4 from terminal_list_watch.",
            },
            "INVALID_SESSION_ID": {
                "description": "session_id is not a UUID4.",
                "solution": "Use the session_id from terminal_session_create.",
            },
            "INVALID_SESSION": {
                "description": "No session for (project_id, session_id).",
                "solution": "terminal_session_create, then retry.",
            },
            "INVALID_SEQ": {
                "description": "seq is missing, not an integer, or less than 1.",
                "solution": "Pass the seq from terminal_run.",
            },
            "NOT_FOUND": {
                "description": "No command record for this seq in session history.",
                "solution": "Verify seq with terminal_list or terminal_get.",
            },
            "NOT_RUNNING": {
                "description": "Command status is not pending (already finished).",
                "solution": "Use terminal_get_status; no kill needed.",
            },
            "KILL_NOT_APPLIED": {
                "description": (
                    "History shows pending but no subprocess was registered (race or "
                    "host run without docker client)."
                ),
                "solution": (
                    "Poll terminal_get_status; retry only if still pending. Host runs "
                    "use terminal_run_host — this command targets sandbox subprocesses."
                ),
            },
        },
        "best_practices": [
            "Confirm seq status is pending via terminal_get_status before killing.",
            "Poll terminal_get_status after kill to see final exit_code.",
            "Do not use terminal_kill for terminal_run_host jobs.",
            "Use terminal_delete to remove the session container and disk state.",
        ],
    }
