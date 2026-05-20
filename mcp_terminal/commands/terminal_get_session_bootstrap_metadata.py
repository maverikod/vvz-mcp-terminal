"""Extended metadata for ``terminal_get_session_bootstrap``."""

from __future__ import annotations

from typing import Any, Dict, Type

_EXAMPLE_PROJECT = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_EXAMPLE_SESSION = "46ce9394-01ca-4440-9c03-c4a7466c4ec5"


def get_terminal_get_session_bootstrap_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Reads ``bootstrap.json`` under ``.terminals/<session_id>/`` and returns the "
            "``runtime_image`` object written at ``terminal_session_create`` when "
            "``bootstrap_python_env`` is true.\n\n"
            "Typical ``runtime_image.status`` values: **pending** (queue job running), "
            "**completed** (image ready or build skipped), **failed** (build failed; session "
            "is kept and stock image may still work).\n\n"
            "When ``bootstrap_python_env`` was false, ``bootstrap.json`` is absent and this "
            "command returns ``NOT_FOUND``. Poll after create until status is no longer "
            "pending before relying on a custom per-project runtime image in ``terminal_run``."
        ),
        "parameters": {
            "project_id": {
                "description": "Project UUID4 for the session.",
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
        },
        "return_value": {
            "success": {
                "description": "Bootstrap state from bootstrap.json.",
                "data": {
                    "runtime_image": (
                        "Object with status (pending|completed|failed), optional job_id "
                        "while pending, and on completion: success, skipped_build, exit_code, "
                        "detail."
                    ),
                },
                "example": {
                    "success": True,
                    "data": {
                        "runtime_image": {
                            "status": "completed",
                            "success": True,
                            "skipped_build": False,
                            "exit_code": 0,
                            "detail": "Runtime image ready.",
                        },
                    },
                },
            },
            "error": {
                "description": "Session or bootstrap state unavailable.",
                "code": "NOT_FOUND",
                "message": "…",
                "details": "…",
            },
        },
        "usage_examples": [
            {
                "description": "Poll after session create with bootstrap enabled",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                },
                "explanation": (
                    "Repeat until runtime_image.status is completed or failed before "
                    "heavy pip installs in terminal_run."
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
            "NOT_FOUND": {
                "description": (
                    "bootstrap.json missing (bootstrap_python_env was false or file "
                    "deleted)."
                ),
                "solution": (
                    "Recreate session with bootstrap_python_env true, or skip polling "
                    "when bootstrap was disabled."
                ),
            },
            "BOOTSTRAP_STATE_CORRUPT": {
                "description": "bootstrap.json exists but runtime_image is not an object.",
                "solution": "Inspect .terminals/<session_id>/bootstrap.json on disk.",
            },
        },
        "best_practices": [
            "Poll after terminal_session_create when bootstrap.status was pending.",
            "Bootstrap failure does not delete the session — check detail before retrying runs.",
            "Use terminal_list_watch to resolve valid project_id values.",
        ],
    }
