"""Extended metadata for ``terminal_session_create``."""

from __future__ import annotations

from typing import Any, Dict, Type

_EXAMPLE_PROJECT = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_EXAMPLE_SESSION = "46ce9394-01ca-4440-9c03-c4a7466c4ec5"


def get_terminal_session_create_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Opens or re-attaches a **terminal session** for the composite key "
            "(project_id, session_id). Both identifiers are **external UUID4 values** "
            "created by the AI editor; the server never generates session_id.\n\n"
            "**On-disk layout** (under the project root):\n"
            "``.terminals/<session_id>/``\n"
            "- ``session.json`` — session metadata (workspace_write flag, timestamps)\n"
            "- ``shell_state.json`` — persisted shell cwd (and optional running container "
            "reference when keep_container was used)\n"
            "- ``history.jsonl`` — append-only command index (like shell history metadata)\n"
            "- ``NNNNNN.stdout.log`` / ``.stderr.log`` / ``.meta.json`` — per-command output\n\n"
            "**Workspace write policy:** at most **one** session per project_id has "
            "``workspace_write: true`` and may use ``terminal_run`` with "
            "``mode: workspace_write``. All other sessions for that project mount "
            "/workspace read-only.\n\n"
            "This command does **not** start the session Docker container. Containers are "
            "started on each ``terminal_run`` (see that command's lifecycle). Optional "
            "``bootstrap_python_env`` only queues a **runtime image build** under "
            "``.mcp_terminal/runtime/`` when ``requirements.txt`` exists.\n\n"
            "**Session defaults (stored in shell_state / session record):**\n"
            "- ``use_venv`` — whether ``terminal_run`` prepends ``/workspace/.venv/bin`` "
            "to PATH (no ``source activate``). Omitted on create: auto true when "
            "``.venv`` exists on the project.\n"
            "- ``pid_namespace`` — Docker PID namespace for this session's containers. "
            "``container`` (default): isolated. ``host``: ``docker run --pid=host`` so "
            "tools on the host (e.g. ``casmgr status``) see daemon PIDs; dev/debug only.\n\n"
            "Typical agent flow: ``terminal_session_create`` → (poll bootstrap if needed) "
            "→ ``terminal_run`` (possibly with ``keep_container: true`` for multi-step work) "
            "→ ``terminal_get_status`` / ``terminal_tail`` → ``terminal_delete`` when done."
        ),
        "parameters": {
            "project_id": {
                "description": (
                    "Project UUID4 from the editor. Must exist in the project registry "
                    "(discovered via projectid under watch directories)."
                ),
                "type": "string",
                "required": True,
                "examples": [_EXAMPLE_PROJECT],
            },
            "session_id": {
                "description": (
                    "Session UUID4 from the editor. Unique together with project_id. "
                    "Reuse the same pair for all commands in one editor terminal tab."
                ),
                "type": "string",
                "required": True,
                "examples": [_EXAMPLE_SESSION],
            },
            "bootstrap_python_env": {
                "description": (
                    "When true (default), enqueue a background job to build or verify a "
                    "per-project Docker image from requirements.txt. Poll with "
                    "terminal_get_session_bootstrap. Failure does not delete the session."
                ),
                "type": "boolean",
                "required": False,
                "default": True,
            },
            "bootstrap_timeout_seconds": {
                "description": "Timeout for the bootstrap docker build job (60–7200).",
                "type": "integer",
                "required": False,
                "default": 1200,
            },
            "image_profile": {
                "description": "Base image recipe for runtime bootstrap.",
                "type": "string",
                "required": False,
                "default": "python_dev_3_12",
                "enum": ["python_dev_3_12", "node_dev_20", "base_tools"],
            },
            "use_venv": {
                "description": (
                    "Session default for ``terminal_run``: prepend /workspace/.venv/bin to "
                    "PATH when true (no activate script). When omitted on create: true if "
                    "project_dir/.venv exists, else false. Can be overridden per "
                    "terminal_run. Updating on an existing session rewrites shell_state "
                    "when the value changes."
                ),
                "type": "boolean",
                "required": False,
            },
            "pid_namespace": {
                "description": (
                    "Docker PID namespace for containers started for this session. "
                    "container (default): normal isolated PID namespace. host: "
                    "--pid=host so host tools (e.g. casmgr) can match daemon PIDs inside "
                    "the container; use only for local dev/debug."
                ),
                "type": "string",
                "required": False,
                "default": "container",
                "enum": ["container", "host"],
            },
        },
        "return_value": {
            "success": {
                "description": "Session exists or was created.",
                "data": {
                    "session_id": "Echo of request session_id.",
                    "project_id": "Echo of request project_id.",
                    "created": "True if a new session directory was created.",
                    "already_exists": "True if (project_id, session_id) was already registered.",
                    "workspace_write": (
                        "True if this session is the sole workspace writer for the project."
                    ),
                    "created_at": "ISO-8601 timestamp.",
                    "reminder": "Short hint about Python/venv and terminal_run behavior.",
                    "venv_ready": "True when project has a usable .venv on disk.",
                    "use_venv": "Resolved session default for PATH/.venv (see use_venv param).",
                    "pid_namespace": "container or host — stored on the session record.",
                    "python": "Path to /workspace/.venv/bin/python when venv_ready and use_venv.",
                    "bootstrap": (
                        "Optional { status: pending, job_id } when bootstrap_python_env is true."
                    ),
                },
                "example": {
                    "success": True,
                    "data": {
                        "session_id": _EXAMPLE_SESSION,
                        "project_id": _EXAMPLE_PROJECT,
                        "created": True,
                        "already_exists": False,
                        "workspace_write": True,
                        "created_at": "2026-05-16T12:00:00+00:00",
                        "venv_ready": True,
                        "use_venv": True,
                        "pid_namespace": "container",
                        "python": "/workspace/.venv/bin/python",
                        "reminder": "Use terminal_run; cwd persists via shell_state.json.",
                        "bootstrap": {"status": "pending", "job_id": "uuid-job"},
                    },
                },
            },
            "error": {
                "description": "Validation or registry failure.",
                "code": "PROJECT_NOT_FOUND",
                "message": "Human-readable detail.",
                "details": "Optional field-level context.",
            },
        },
        "usage_examples": [
            {
                "description": "Open a new editor terminal session",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "bootstrap_python_env": True,
                },
                "explanation": (
                    "Creates .terminals/<session_id>/ with shell_state.json (cwd '.'). "
                    "Queues runtime image build if requirements.txt exists."
                ),
            },
            {
                "description": "Idempotent re-open after server restart",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "bootstrap_python_env": False,
                },
                "explanation": (
                    "If the directory already exists on disk, returns already_exists: true "
                    "and adopts shell_state/history without losing cwd."
                ),
            },
            {
                "description": "Host PID namespace for casmgr from inside container",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "pid_namespace": "host",
                    "bootstrap_python_env": False,
                    "use_venv": True,
                },
                "explanation": (
                    "terminal_run containers use --pid=host so casmgr status from "
                    "/workspace can see the code-analysis-server daemon on the host."
                ),
            },
        ],
        "error_cases": {
            "INVALID_PROJECT_ID": {
                "description": "project_id is not a valid UUID4.",
                "message": "Stable error code in error field.",
                "solution": "Use a UUID4 from the editor or terminal_list_watch.",
            },
            "INVALID_SESSION_ID": {
                "description": "session_id is not a valid UUID4.",
                "message": "Stable error code in error field.",
                "solution": "Generate a new UUID4 in the editor for this terminal tab.",
            },
            "PROJECT_NOT_FOUND": {
                "description": "project_id is not in the registry.",
                "message": "Project not found.",
                "solution": "Call terminal_list_watch and use an enabled project_id.",
            },
            "SESSION_STATE_CORRUPT": {
                "description": "Session directory exists but session.json is missing or invalid.",
                "message": "SESSION_STATE_CORRUPT",
                "solution": (
                    "terminal_delete with force or remove .terminals/<session_id> manually."
                ),
            },
            "SESSION_PROJECT_MISMATCH": {
                "description": "On-disk session.json project_id/session_id does not match request.",
                "message": "SESSION_PROJECT_MISMATCH",
                "solution": "Use matching UUIDs or a new session_id.",
            },
            "INVALID_PID_NAMESPACE": {
                "description": "pid_namespace is not container or host.",
                "message": "INVALID_PID_NAMESPACE",
                "solution": "Omit the field or use enum value container or host.",
            },
        },
        "best_practices": [
            (
                "Generate session_id once per editor terminal tab and reuse it "
                "for all terminal_run calls."
            ),
            "Call terminal_session_create before the first terminal_run for that pair.",
            "Check workspace_write in the response before using mode workspace_write.",
            (
                "Poll terminal_get_session_bootstrap when bootstrap.status is "
                "pending before heavy pip installs."
            ),
            "Set pid_namespace host only when host-side process tools must see daemon PIDs.",
            "Set use_venv false when the project has no .venv and system Python is intended.",
            (
                "Call terminal_delete when the editor tab closes to remove "
                "the session container and disk state."
            ),
        ],
    }
