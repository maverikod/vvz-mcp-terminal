"""Extended metadata for ``terminal_get_status``."""

from __future__ import annotations

from typing import Any, Dict, Type


def get_terminal_get_status_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Polls adapter queue status and terminal command completion for one "
            "``terminal_run``, ``terminal_run_host``, or future attached-target run "
            "seq. **Queue completed ≠ command succeeded** — always check "
            "``exit_code`` and ``timed_out`` when the queue shows completion.\n\n"
            "``execution_target`` is read from ``NNNNNN.meta.json`` when present: "
            "``sandbox`` (Docker sandbox from ``terminal_run``), ``host`` "
            "(``terminal_run_host``), or ``attached`` (future). Legacy meta values "
            "``container`` are reported as ``sandbox``.\n\n"
            "Use the same project_id and session_id as the run command. Typical loop: "
            "terminal_run (or terminal_run_host) → terminal_get_status (repeat) → "
            "terminal_tail."
        ),
        "parameters": {
            "project_id": {"description": "Project UUID4.", "type": "string", "required": True},
            "session_id": {"description": "Session UUID4.", "type": "string", "required": True},
            "seq": {
                "description": "seq returned by terminal_run.",
                "type": "integer",
                "required": True,
            },
        },
        "return_value": {
            "success": {
                "description": "Status snapshot for one session-local seq.",
                "data": {
                    "job_id": "Adapter queue job id when enqueued.",
                    "queue_status": (
                        "Adapter job state (pending, running, completed, failed, …)."
                    ),
                    "terminal_status": (
                        "Derived terminal outcome: success, failure, timed_out, or "
                        "mirrors queue_status while still pending."
                    ),
                    "exit_code": "Shell exit code from meta when completed; null while pending.",
                    "timed_out": "True when the run hit timeout_seconds.",
                    "execution_target": (
                        "Where the command ran: ``sandbox``, ``host``, or ``attached``. "
                        "Read from ``NNNNNN.meta.json``; omitted if meta has no field yet. "
                        "Legacy meta value ``container`` is returned as ``sandbox``."
                    ),
                    "stdout_file": "Relative stdout log name under the session dir.",
                    "stderr_file": "Relative stderr log name under the session dir.",
                    "stdout_bytes": "Current stdout file size in bytes.",
                    "stderr_bytes": "Current stderr file size in bytes.",
                },
                "example": {
                    "success": True,
                    "data": {
                        "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "queue_status": "completed",
                        "terminal_status": "success",
                        "exit_code": 0,
                        "timed_out": False,
                        "execution_target": "host",
                        "stdout_file": "000001.stdout.log",
                        "stderr_file": "000001.stderr.log",
                        "stdout_bytes": 128,
                        "stderr_bytes": 0,
                    },
                },
            },
            "error": {
                "description": "Unknown session or seq.",
                "code": "INVALID_SESSION",
                "message": "…",
                "details": "…",
            },
        },
        "usage_examples": [
            {
                "description": "Poll after terminal_run",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "46ce9394-01ca-4440-9c03-c4a7466c4ec5",
                    "seq": 1,
                },
                "explanation": "Repeat until queue and terminal show completion.",
            },
        ],
        "error_cases": {
            "INVALID_SESSION": {
                "description": "Session not found.",
                "solution": "terminal_session_create.",
            },
        },
        "best_practices": [
            "Do not assume success when queue status is completed.",
            "Use execution_target to choose the right follow-up (sandbox logs vs host policy).",
            "Read stdout via terminal_tail after exit_code is known.",
        ],
    }
