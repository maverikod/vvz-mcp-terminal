"""Extended metadata for ``terminal_get``."""

from __future__ import annotations

from typing import Any, Dict, Type

_EXAMPLE_PROJECT = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_EXAMPLE_SESSION = "46ce9394-01ca-4440-9c03-c4a7466c4ec5"


def get_terminal_get_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Returns **full metadata** for one command in a session, identified by "
            "exact ``seq``. Data comes from the ``history.jsonl`` entry: launch time, "
            "status, exit code, execution kind, shell command or argv, resolved argv, "
            "cwd, sandbox mode/network/image profile, output file names, and adapter "
            "``job_id`` when present.\n\n"
            "This is a **read-only** lookup. It does not read stdout/stderr bytes — "
            "use ``terminal_read`` or ``terminal_tail`` for output. For queue and "
            "completion while a run is active, use ``terminal_get_status``.\n\n"
            "If ``seq`` does not exist in the session history, the command returns "
            "``NOT_FOUND``."
        ),
        "parameters": {
            "project_id": {
                "description": "Project UUID4.",
                "type": "string",
                "required": True,
                "examples": [_EXAMPLE_PROJECT],
            },
            "session_id": {
                "description": "Session UUID4.",
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
                "examples": [1, 2],
            },
        },
        "return_value": {
            "success": {
                "description": "Full command record for the requested seq.",
                "data": {
                    "seq": "Session-local sequence number.",
                    "timestamp": "ISO-8601 launch time.",
                    "status": "Terminal command status.",
                    "exit_code": "Shell exit code when completed.",
                    "timed_out": "True when the run hit timeout_seconds.",
                    "execution_kind": "shell or argv.",
                    "command": "Original shell command string, or null for argv runs.",
                    "argv": "Argv list when execution_kind is argv.",
                    "resolved_argv": "Argv actually executed after policy resolution.",
                    "cwd": "Project-relative working directory for the run.",
                    "mode": "Sandbox mode from the run request.",
                    "network": "Network policy label for the run.",
                    "image_profile": "Container image profile for sandbox runs.",
                    "stdout_file": "Relative stdout log name (e.g. 000001.stdout.log).",
                    "stderr_file": "Relative stderr log name.",
                    "meta_file": "Relative meta JSON path.",
                    "job_id": "Adapter queue job id when enqueued.",
                },
                "example": {
                    "success": True,
                    "data": {
                        "seq": 1,
                        "timestamp": "2026-05-20T11:59:00Z",
                        "status": "completed",
                        "exit_code": 0,
                        "timed_out": False,
                        "execution_kind": "shell",
                        "command": "pytest -q",
                        "argv": None,
                        "resolved_argv": ["bash", "-lc", "pytest -q"],
                        "cwd": ".",
                        "mode": "default",
                        "network": "none",
                        "image_profile": "default",
                        "stdout_file": "000001.stdout.log",
                        "stderr_file": "000001.stderr.log",
                        "meta_file": "000001.meta.json",
                        "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    },
                },
            },
            "error": {
                "description": "Unknown session or seq not in history.",
                "code": "NOT_FOUND",
                "message": "NOT_FOUND or INVALID_SESSION",
                "details": "…",
            },
        },
        "usage_examples": [
            {
                "description": "Fetch metadata for seq 1 after terminal_run",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "seq": 1,
                },
                "explanation": (
                    "Use stdout_file and stderr_file with terminal_tail or terminal_read."
                ),
            },
            {
                "description": "Inspect argv and cwd for a host run",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "seq": 2,
                },
                "explanation": (
                    "Host runs still record execution_kind, argv, and output file names "
                    "in history.jsonl."
                ),
            },
        ],
        "error_cases": {
            "INVALID_PROJECT_ID": {
                "description": "project_id is not a valid UUID4.",
                "message": "INVALID_PROJECT_ID",
                "solution": "Use a valid project UUID4.",
            },
            "INVALID_SESSION_ID": {
                "description": "session_id is not a valid UUID4.",
                "message": "INVALID_SESSION_ID",
                "solution": "Use the session_id from terminal_session_create.",
            },
            "INVALID_SESSION": {
                "description": "No session directory for (project_id, session_id).",
                "message": "INVALID_SESSION",
                "solution": "Call terminal_session_create before terminal_get.",
            },
            "NOT_FOUND": {
                "description": "seq is not present in session history.jsonl.",
                "message": "NOT_FOUND",
                "solution": (
                    "Call terminal_list to see valid seq values, or wait until "
                    "terminal_run returns a seq."
                ),
            },
        },
        "best_practices": [
            "Discover seq with terminal_list, then terminal_get for full fields.",
            (
                "Use terminal_get_status for queue/exit polling; "
                "terminal_get is a static history snapshot."
            ),
            "Read output with terminal_tail using stdout_file from this response.",
            "job_id may be null for records not yet linked to the adapter queue.",
        ],
    }
