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
            "``terminal_run`` seq. **Queue completed ≠ command succeeded** — always "
            "check ``exit_code`` and ``timed_out`` in the terminal section when status "
            "is completed.\n\n"
            "Use the same project_id and session_id as terminal_run. Typical loop: "
            "terminal_run → terminal_get_status (repeat) → terminal_tail."
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
                "description": "Status snapshot.",
                "data": {
                    "queue": "Adapter job state.",
                    "terminal": "exit_code, timed_out, meta from 000NNN.meta.json.",
                },
                "example": {"success": True, "data": {}},
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
            "Read stdout via terminal_tail after exit_code is known.",
        ],
    }
