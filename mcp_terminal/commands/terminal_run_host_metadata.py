"""Extended metadata for ``terminal_run_host``."""

from __future__ import annotations

from typing import Any, Dict, Type

_EXAMPLE_PROJECT = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_EXAMPLE_SESSION = "46ce9394-01ca-4440-9c03-c4a7466c4ec5"


def get_terminal_run_host_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Runs one command **on the host filesystem** (outside Docker) for an existing "
            "terminal session. This command is **separate** from ``terminal_run``, which "
            "always uses the sandbox container lifecycle.\n\n"
            "**Server config (required):**\n"
            "- ``terminal.host_execution.enabled`` must be ``true`` (default in generated "
            "config is ``false``).\n"
            "- ``terminal.host_execution.allowed_commands`` must list the executable "
            "basenames you intend to run (e.g. ``casmgr``, ``pytest``, ``git``).\n"
            "If host execution is disabled or the allowlist is empty, the command returns "
            "``HOST_EXECUTION_DISABLED`` before queueing.\n\n"
            "**Validation:** shell chains (``&&``, ``||``, ``;``, ``|``) are decomposed; "
            "every segment's executable must be on the allowlist. Redirect targets, "
            "here-strings (``<<<``), and heredoc bodies are scanned for forbidden patterns "
            "(``--pid=host``, ``/var/run/docker.sock``, ``$(...)``, etc.). Some executables "
            "(``docker``, ``sudo``, …) are always forbidden on the host path.\n\n"
            "**Asynchronous:** returns immediately with ``job_id`` and ``seq``. Poll "
            "``terminal_get_status`` with the same ``project_id``, ``session_id``, and "
            "``seq``. Read output via ``terminal_tail`` / ``terminal_read``. Queue "
            "completion does not imply the shell command succeeded (check ``exit_code``).\n\n"
            "**Safety:** host execution can modify the real project tree and interact with "
            "host daemons. Keep ``enabled`` false unless a trusted operator explicitly "
            "needs host-side tools (e.g. ``casmgr`` against a host code-analysis daemon)."
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
            "execution_kind": {
                "description": (
                    "``shell``: run ``command`` string in bash after ``cd`` to saved cwd. "
                    "``argv``: run explicit argument list (preferred for allowlisted tools)."
                ),
                "type": "string",
                "required": True,
                "enum": ["shell", "argv"],
            },
            "command": {
                "description": (
                    "Required when execution_kind is shell. Simple chains allowed when "
                    "every segment passes allowlist and forbidden checks. Prefer ``argv`` "
                    "for single-tool invocations."
                ),
                "type": "string",
                "required": False,
                "examples": ["casmgr --config config.json status"],
            },
            "argv": {
                "description": "Required when execution_kind is argv. First element is the executable basename checked against the allowlist.",
                "type": "array",
                "required": False,
                "items": {"type": "string"},
                "examples": [["casmgr", "--config", "config.json", "status"]],
            },
            "cwd": {
                "description": (
                    "Optional project-relative working directory for this run on the host. "
                    "If omitted, uses ``shell_state.json`` cwd from the previous "
                    "terminal_run or terminal_run_host."
                ),
                "type": "string",
                "required": False,
                "default": "(from shell_state.json, usually '.')",
                "examples": ["tests", "src/pkg"],
            },
            "timeout_seconds": {
                "description": "Maximum wall time in seconds before SIGKILL on the host process.",
                "type": "integer",
                "required": False,
                "default": 600,
            },
            "use_venv": {
                "description": (
                    "When omitted, uses session default from shell_state.json. When true, "
                    "prepends ``<project>/.venv/bin`` to PATH on the host (no "
                    "``source activate``). When false, system PATH only."
                ),
                "type": "boolean",
                "required": False,
            },
        },
        "return_value": {
            "success": {
                "description": "Host job enqueued; execution runs in a background queue worker.",
                "data": {
                    "job_id": "Adapter queue job id for terminal_get_status.",
                    "seq": "Session-local monotonic command number (1, 2, 3, …).",
                    "stdout_file": "Relative name under .terminals/<session_id>/ (e.g. 000001.stdout.log).",
                    "stderr_file": "Relative name under .terminals/<session_id>/ (e.g. 000001.stderr.log).",
                    "meta_file": "Relative meta JSON (exit_code, timed_out, execution_target after completion).",
                    "cwd": "Effective project-relative cwd used for this run.",
                    "use_venv": "Echo of resolved use_venv flag.",
                    "execution_target": "Always ``host`` for this command.",
                },
                "example": {
                    "success": True,
                    "data": {
                        "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "seq": 1,
                        "stdout_file": "000001.stdout.log",
                        "stderr_file": "000001.stderr.log",
                        "meta_file": "000001.meta.json",
                        "cwd": ".",
                        "use_venv": True,
                        "execution_target": "host",
                    },
                },
            },
            "error": {
                "description": "Rejected before queueing (config, policy, or missing session).",
                "code": "HOST_EXECUTION_DISABLED",
                "message": "Stable ErrorContract code.",
                "details": "Optional field-level hint from validation.",
            },
        },
        "usage_examples": [
            {
                "description": "Host-side casmgr status (argv)",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "execution_kind": "argv",
                    "argv": ["casmgr", "--config", "config.json", "status"],
                },
                "explanation": (
                    "Requires terminal.host_execution.enabled and ``casmgr`` in "
                    "allowed_commands. Poll terminal_get_status, then terminal_tail."
                ),
            },
            {
                "description": "Chained allowlisted commands in shell mode",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "execution_kind": "shell",
                    "command": "pytest -q && git status",
                },
                "explanation": (
                    "Both ``pytest`` and ``git`` must be on the allowlist; forbidden "
                    "patterns in redirects or heredocs still fail validation."
                ),
            },
            {
                "description": "Continue from saved cwd with venv on PATH",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "execution_kind": "argv",
                    "argv": ["python", "-m", "build"],
                    "use_venv": True,
                },
                "explanation": (
                    "Omit cwd to use shell_state.json; ``python`` must be allowlisted."
                ),
            },
        ],
        "error_cases": {
            "HOST_EXECUTION_DISABLED": {
                "description": (
                    "terminal.host_execution.enabled is false or allowed_commands is empty."
                ),
                "message": "HOST_EXECUTION_DISABLED",
                "solution": (
                    "Set terminal.host_execution.enabled to true and populate "
                    "allowed_commands in term_server.json, then restart the server. "
                    "Use terminal_run for sandboxed work when host tools are not needed."
                ),
            },
            "HOST_COMMAND_NOT_ALLOWED": {
                "description": (
                    "Executable basename not in allowed_commands, empty argv/command, or "
                    "invalid chain segment."
                ),
                "message": "HOST_COMMAND_NOT_ALLOWED",
                "solution": (
                    "Add the tool basename to terminal.host_execution.allowed_commands "
                    "or simplify the command. Use execution_kind argv with an explicit "
                    "allowlisted executable."
                ),
            },
            "HOST_FORBIDDEN_COMMAND": {
                "description": (
                    "Forbidden substring in command, segment, redirect target, here-string, "
                    "or heredoc body; or a hard-blocked executable (docker, sudo, …)."
                ),
                "message": "HOST_FORBIDDEN_COMMAND",
                "solution": (
                    "Remove forbidden syntax (e.g. --pid=host, command substitution). "
                    "Use terminal_run for unrestricted sandbox shell when appropriate."
                ),
            },
            "INVALID_SESSION": {
                "description": "No session directory for (project_id, session_id).",
                "message": "INVALID_SESSION",
                "solution": "Call terminal_session_create before terminal_run_host.",
            },
            "INVALID_CWD": {
                "description": "cwd is absolute, contains .., or invalid characters.",
                "message": "INVALID_CWD",
                "solution": "Use a project-relative path such as tests or src/pkg.",
            },
            "INVALID_COMMAND": {
                "description": (
                    "execution_kind missing/invalid, argv not a list, or command/argv "
                    "inconsistent with execution_kind."
                ),
                "message": "INVALID_COMMAND",
                "solution": "Set execution_kind to shell or argv and supply matching command or argv.",
            },
            "PROJECT_NOT_FOUND": {
                "description": "project_id is unknown to the project registry.",
                "message": "PROJECT_NOT_FOUND",
                "solution": "Call terminal_list_watch and use a valid project_id.",
            },
        },
        "best_practices": [
            "Keep terminal.host_execution.enabled false by default; enable only for dev/debug host daemon workflows.",
            "Use terminal_run for normal project work inside the Docker sandbox.",
            "Prefer execution_kind argv with an explicit allowlisted executable (casmgr, pytest, git).",
            "Always terminal_session_create before the first terminal_run_host for a session.",
            "Poll terminal_get_status until queue and terminal status are completed before reading exit_code.",
            "Do not assume success when the queue job completes; check exit_code and timed_out in meta.",
            "Populate allowed_commands with basenames only (casmgr, not /usr/bin/casmgr).",
            "After changing host_execution in config, restart the term server.",
        ],
    }
