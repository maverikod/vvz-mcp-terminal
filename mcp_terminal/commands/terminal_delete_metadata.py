"""Extended metadata for ``terminal_delete``."""

from __future__ import annotations

from typing import Any, Dict, Type

_EXAMPLE_PROJECT = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_EXAMPLE_SESSION = "46ce9394-01ca-4440-9c03-c4a7466c4ec5"


def get_terminal_delete_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Deletes a terminal session for the composite key (project_id, session_id).\n\n"
            "**Container cleanup:** always runs ``docker rm -f`` on the session container "
            "(name ``mcp-term-<hash>``) if it exists, including containers left running by "
            "``terminal_run`` with ``keep_container: true``.\n\n"
            "**Disk cleanup:** removes the entire ``.terminals/<session_id>/`` tree: "
            "shell_state.json, history.jsonl, stdout/stderr logs, and bootstrap files.\n\n"
            "**Workspace write lock:** if this session was the project workspace writer, "
            "the write slot is released so another session can become writer.\n\n"
            "If the session is not registered but the directory is already gone, returns "
            "success with deleted: true (idempotent)."
        ),
        "parameters": {
            "project_id": {
                "description": "Project UUID4.",
                "type": "string",
                "required": True,
                "examples": [_EXAMPLE_PROJECT],
            },
            "session_id": {
                "description": "Session UUID4 to delete.",
                "type": "string",
                "required": True,
                "examples": [_EXAMPLE_SESSION],
            },
            "force": {
                "description": (
                    "When true, delete even if session status is running. Default false."
                ),
                "type": "boolean",
                "required": False,
                "default": False,
            },
        },
        "return_value": {
            "success": {
                "description": "Session removed or was already absent.",
                "data": {
                    "deleted": "Always true on success.",
                    "project_id": "Echo.",
                    "session_id": "Echo.",
                },
                "example": {
                    "success": True,
                    "data": {
                        "deleted": True,
                        "project_id": _EXAMPLE_PROJECT,
                        "session_id": _EXAMPLE_SESSION,
                    },
                },
            },
            "error": {
                "description": "Delete refused or validation failed.",
                "code": "SESSION_RUNNING",
                "message": "…",
                "details": "…",
            },
        },
        "usage_examples": [
            {
                "description": "Close editor terminal tab",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                },
                "explanation": (
                    "Stops session Docker container and deletes .terminals/<session_id>/."
                ),
            },
        ],
        "error_cases": {
            "INVALID_PROJECT_ID": {
                "description": "project_id not UUID4.",
                "solution": "Fix UUID.",
            },
            "INVALID_SESSION_ID": {
                "description": "session_id not UUID4.",
                "solution": "Fix UUID.",
            },
            "SESSION_RUNNING": {
                "description": "Session marked running and force is false.",
                "solution": "Wait for terminal_run to finish or use force: true.",
            },
        },
        "best_practices": [
            "Call terminal_delete when the editor closes a terminal tab.",
            (
                "Set keep_container false on the last terminal_run before delete "
                "(optional; delete stops container anyway)."
            ),
            "Use force only when a stuck session blocks cleanup.",
        ],
    }
