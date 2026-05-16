"""Extended metadata for ``terminal_run``."""

from __future__ import annotations

from typing import Any, Dict, Type

_EXAMPLE_PROJECT = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_EXAMPLE_SESSION = "46ce9394-01ca-4440-9c03-c4a7466c4ec5"


def get_terminal_run_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Runs one command (or a **batch** as a single shell string with ``&&``, ``;``, "
            "pipelines) inside an isolated Docker sandbox for an existing session.\n\n"
            "**Always asynchronous:** returns immediately with ``job_id`` and ``seq``. "
            "Poll ``terminal_get_status`` with the same project_id, session_id, and seq. "
            "Read output via ``terminal_tail`` or ``terminal_read``. Queue completion does "
            "not imply the shell command succeeded (check exit_code).\n\n"
            "## Session container lifecycle (each job)\n\n"
            "Unless a compatible container is already running from a prior "
            "``keep_container: true`` run:\n\n"
            "1. **Start** — ``docker run -d`` idle container (``sleep infinity``), name "
            "``mcp-term-<hash>``, label ``mcp.terminal.session=true``.\n"
            "2. **Load state** — read ``.terminals/<session_id>/shell_state.json`` "
            "(field ``cwd``, default ``\".\"``). Mount session dir at ``/session-state``.\n"
            "3. **Execute** — ``docker exec`` runs a script: ``cd`` to saved cwd under "
            "/workspace, then your shell/argv command.\n"
            "4. **Save state** — after the command, cwd relative to /workspace is written "
            "back to ``shell_state.json`` (simulated persistent shell directory).\n"
            "5. **Stop** — if ``keep_container`` is false (default), ``docker rm -f`` the "
            "session container. If true, container stays up for the next terminal_run.\n\n"
            "**Mounts:** project root → ``/workspace`` (ro or rw per workspace_write); "
            "``.terminals/<session_id>/`` → ``/session-state`` (rw); tmpfs ``/tmp`` and "
            "``/scratch``. Root filesystem is read-only; capabilities dropped.\n\n"
            "**cwd parameter:** optional override for this run only. If omitted, uses "
            "``shell_state.json`` from the previous command. After ``cd`` inside the "
            "command, the new cwd is saved for the next run.\n\n"
            "**keep_container:** set true for long multi-step work (install, test, build) "
            "to avoid container start/stop overhead between commands. Set false when "
            "finished or before terminal_delete.\n\n"
            "**Not a TTY:** ``command: bash`` does not open an interactive shell; it exits "
            "immediately. Use shell strings with explicit commands.\n\n"
            "**Python venv:** ``source .venv/bin/activate`` does not persist across runs "
            "unless you use keep_container and run activate once, then subsequent runs in "
            "the same kept container. Prefer ``/workspace/.venv/bin/python`` or "
            "``. .venv/bin/activate && ...`` in one shell command."
        ),
        "parameters": {
            "project_id": {
                "description": "Project UUID4 (must match terminal_session_create).",
                "type": "string",
                "required": True,
                "examples": [_EXAMPLE_PROJECT],
            },
            "session_id": {
                "description": "Session UUID4 from the editor.",
                "type": "string",
                "required": True,
                "examples": [_EXAMPLE_SESSION],
            },
            "execution_kind": {
                "description": "shell (string command) or argv (explicit argument list).",
                "type": "string",
                "required": True,
                "enum": ["shell", "argv"],
            },
            "command": {
                "description": (
                    "Shell command when execution_kind is shell. May chain commands "
                    "(batch) with && or ;. cwd changes inside this string are persisted."
                ),
                "type": "string",
                "required": False,
                "examples": ["cd tests && pytest -q"],
            },
            "argv": {
                "description": "Argv list when execution_kind is argv.",
                "type": "array",
                "required": False,
                "items": {"type": "string"},
            },
            "cwd": {
                "description": (
                    "Optional project-relative working directory for this run. "
                    "If omitted, uses shell_state.json cwd from the previous terminal_run."
                ),
                "type": "string",
                "required": False,
                "default": "(from shell_state.json, usually '.')",
                "examples": ["tests", "src/pkg"],
            },
            "keep_container": {
                "description": (
                    "When false (default): stop and remove the session container after "
                    "saving shell_state (normal one-shot cycle). When true: leave the "
                    "container running for the next terminal_run with the same "
                    "(project_id, session_id) for faster multi-step workflows."
                ),
                "type": "boolean",
                "required": False,
                "default": False,
            },
            "mode": {
                "description": (
                    "read_only (default): /workspace ro. workspace_write: rw if this session "
                    "has workspace_write. scratch_write: /workspace ro, use /scratch for writes."
                ),
                "type": "string",
                "required": False,
                "default": "read_only",
                "enum": ["read_only", "workspace_write", "scratch_write"],
            },
            "network": {
                "description": "none (default) or package_registry for pip/apt egress.",
                "type": "string",
                "required": False,
                "default": "none",
                "enum": ["none", "package_registry"],
            },
            "image_profile": {
                "description": (
                    "Stock profile or local mcp-terminal:pid-* image when bootstrap succeeded."
                ),
                "type": "string",
                "required": False,
                "default": "python_dev_3_12",
                "enum": ["python_dev_3_12", "node_dev_20", "base_tools"],
            },
            "timeout_seconds": {
                "description": "Max seconds for docker exec (default 600).",
                "type": "integer",
                "required": False,
                "default": 600,
            },
        },
        "return_value": {
            "success": {
                "description": "Job enqueued; container cycle runs in background.",
                "data": {
                    "job_id": "Adapter queue job id for terminal_get_status.",
                    "seq": "Session-local monotonic command number (1, 2, 3, …).",
                    "stdout_file": "Relative name under .terminals/<session_id>/.",
                    "stderr_file": "Relative name under .terminals/<session_id>/.",
                    "meta_file": "Relative meta JSON (exit_code after completion).",
                    "cwd": "Effective cwd used for this run.",
                    "keep_container": "Echo of request flag.",
                },
                "example": {
                    "success": True,
                    "data": {
                        "job_id": "a1b2c3d4-…",
                        "seq": 1,
                        "stdout_file": "000001.stdout.log",
                        "stderr_file": "000001.stderr.log",
                        "meta_file": "000001.meta.json",
                        "cwd": ".",
                        "keep_container": False,
                    },
                },
            },
            "error": {
                "description": "Rejected before queueing.",
                "code": "INVALID_SESSION",
                "message": "Stable error code.",
                "details": "Optional.",
            },
        },
        "usage_examples": [
            {
                "description": "Single command with persisted cwd",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "execution_kind": "shell",
                    "command": "cd tests && ls",
                },
                "explanation": (
                    "After completion, shell_state.json cwd becomes 'tests'. Next run without "
                    "cwd param starts in tests/."
                ),
            },
            {
                "description": "Long install without stopping container between steps",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "execution_kind": "shell",
                    "command": "python -m pip install -r requirements.txt",
                    "network": "package_registry",
                    "keep_container": True,
                    "mode": "workspace_write",
                },
                "explanation": (
                    "Container stays up. Follow with another terminal_run (keep_container true "
                    "or false); then set keep_container false when done."
                ),
            },
            {
                "description": "Override cwd for one run only",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "execution_kind": "shell",
                    "command": "pwd",
                    "cwd": "src",
                },
                "explanation": (
                    "Runs in src/; if the command does not cd elsewhere, "
                    "shell_state cwd updates from pwd after run."
                ),
            },
        ],
        "error_cases": {
            "INVALID_SESSION": {
                "description": "No terminal_session_create for this (project_id, session_id).",
                "solution": "Call terminal_session_create first.",
            },
            "WORKSPACE_WRITE_NOT_ALLOWED": {
                "description": "mode workspace_write but session lacks workspace_write.",
                "solution": "Use read_only or open the writer session for this project.",
            },
            "INVALID_CWD": {
                "description": "cwd absolute, contains .., or invalid characters.",
                "solution": "Use a project-relative path like tests/unit.",
            },
            "INVALID_COMMAND": {
                "description": "Policy rejected command or argv.",
                "solution": "Simplify command; avoid forbidden docker/host patterns.",
            },
            "PROJECT_NOT_FOUND": {
                "description": "project_id not in registry.",
                "solution": "terminal_list_watch.",
            },
        },
        "best_practices": [
            "Always terminal_session_create before the first terminal_run for a session.",
            (
                "Poll terminal_get_status until queue and terminal status are "
                "terminal before assuming success."
            ),
            (
                "Use keep_container true for sequences of related commands; "
                "end with keep_container false."
            ),
            "Omit cwd to continue from the previous directory; pass cwd to jump explicitly.",
            "Use /workspace/.venv/bin/python when not using keep_container after activate.",
            (
                "Call terminal_delete when done to remove the session container "
                "and .terminals directory."
            ),
        ],
    }
