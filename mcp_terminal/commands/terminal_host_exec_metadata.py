"""Extended metadata for ``terminal_host_exec``."""

from __future__ import annotations

from typing import Any, Dict, Type

from mcp_terminal.commands.metadata_common import (
    CASMGR_SESSION_ERROR_CASES,
    merge_error_cases,
)

_EXAMPLE_PROJECT = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_EXAMPLE_SESSION = "46ce9394-01ca-4440-9c03-c4a7466c4ec5"


def get_terminal_host_exec_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Runs one configured command on the **real host** via SSH. By default it "
            "does not require a terminal session; legacy project/session mode is still "
            "accepted when both ``project_id`` and ``session_id`` are supplied. "
            "This command is **separate** from ``terminal_run``, which "
            "always uses the sandbox container lifecycle.\n\n"
            "**Server config (required when enabled):**\n"
            "- ``terminal.host_execution.enabled`` must be ``true`` (default is ``false``).\n"
            "- Either ``terminal.host_execution.allowed_commands`` must list executable "
            "basenames or ``terminal.host_execution.full_access`` must be ``true``.\n"
            "- ``terminal.host_execution.secrets_path`` must point to an existing private "
            "directory for host-exec SSH key material.\n"
            "- ``terminal.host_execution.ssh`` must define ``host``, ``target_users``, "
            "and ``known_hosts_path`` (StrictHostKeyChecking=yes; no silent host-key bypass).\n"
            "If host execution is disabled, allowed_commands is empty while full_access is "
            "false, secrets_path is unsafe, or SSH settings are "
            "incomplete, the command returns ``HOST_EXECUTION_DISABLED`` before queueing.\n\n"
            "**SSH model:** sessionless host exec uses the stable ``host_exec`` key under "
            "``terminal.host_execution.secrets_path``. Legacy session mode uses the session "
            "key. Commands run as ``target_user`` on the real host sshd — not inside the "
            "service container.\n\n"
            "**Validation:** by default allowlist + forbidden-pattern scan + key-guard "
            "(commands referencing the session private key path are rejected). With "
            "``full_access=true``, allowlist and forbidden-pattern checks are bypassed; "
            "SSH, target_user, secrets_path, and key-guard checks remain active.\n\n"
            "**Asynchronous:** returns immediately with ``job_id`` and ``seq``. Poll "
            "``terminal_get_status``; read output via ``terminal_tail`` / ``terminal_read``.\n\n"
            "**Safety:** host execution modifies the real project tree. Keep ``enabled`` false "
            "unless a trusted operator explicitly needs host-side tools."
        ),
        "parameters": {
            "project_id": {
                "description": (
                    "Optional legacy project UUID4. If set, session_id must also be set. "
                    "Omit both project_id and session_id for sessionless host execution."
                ),
                "type": "string",
                "required": False,
                "examples": [_EXAMPLE_PROJECT],
            },
            "session_id": {
                "description": (
                    "Optional legacy session UUID4 from terminal_session_create. If set, "
                    "project_id must also be set."
                ),
                "type": "string",
                "required": False,
                "examples": [_EXAMPLE_SESSION],
            },
            "execution_kind": {
                "description": (
                    "``shell``: run ``command`` string in bash after ``cd`` to saved cwd. "
                    "``argv``: run explicit argument list (preferred for configured tools)."
                ),
                "type": "string",
                "required": True,
                "enum": ["shell", "argv"],
            },
            "command": {
                "description": (
                    "Required when execution_kind is shell. Simple chains allowed when "
                    "every segment passes configured policy checks."
                ),
                "type": "string",
                "required": False,
                "examples": ["pytest -q && git status"],
            },
            "argv": {
                "description": (
                    "Required when execution_kind is argv. First element is the executable "
                    "basename checked against the allowlist unless full_access is true."
                ),
                "type": "array",
                "required": False,
                "items": {"type": "string"},
                "examples": [["hostname"]],
            },
            "target_user": {
                "description": (
                    "SSH login on the real host. Must appear in "
                    "``terminal.host_execution.ssh.target_users``. "
                    "When omitted, the first configured target user is used."
                ),
                "type": "string",
                "required": False,
                "notes": "Configured in term_server.json under terminal.host_execution.ssh.",
            },
            "cwd": {
                "description": (
                    "Sessionless mode: optional absolute host working directory, default "
                    "``/root``. Legacy session mode: optional project-relative working "
                    "directory."
                ),
                "type": "string",
                "required": False,
                "default": "/root in sessionless mode",
                "examples": ["/root", "/var/log", "tests"],
            },
            "timeout_seconds": {
                "description": "Maximum wall time in seconds before SIGKILL on the remote process.",
                "type": "integer",
                "required": False,
                "default": 600,
            },
            "use_venv": {
                "description": (
                    "Sessionless mode defaults to false. Legacy session mode uses the session "
                    "default when omitted; true prepends ``<project>/.venv/bin`` to PATH."
                ),
                "type": "boolean",
                "required": False,
            },
        },
        "return_value": {
            "success": {
                "description": "Host SSH job enqueued; execution runs in a background queue worker.",
                "data": {
                    "job_id": "Adapter queue job id for terminal_get_status.",
                    "seq": "Session-local monotonic command number (1, 2, 3, …).",
                    "stdout_file": "Relative name under .terminals/<session_id>/ (e.g. 000001.stdout.log).",
                    "stderr_file": "Relative name under .terminals/<session_id>/ (e.g. 000001.stderr.log).",
                    "meta_file": "Relative meta JSON (exit_code, timed_out, execution_target after completion).",
                    "cwd": "Effective project-relative cwd used for this run.",
                    "use_venv": "Echo of resolved use_venv flag.",
                    "target_user": "SSH login used on the real host.",
                    "execution_target": "Always ``host_ssh`` for this command.",
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
                        "target_user": "mcp-terminal-host",
                        "execution_target": "host_ssh",
                    },
                },
            },
            "error": {
                "description": "Rejected before queueing (config, policy, SSH, or missing session).",
                "code": "HOST_EXECUTION_DISABLED",
                "message": "Stable ErrorContract code.",
                "details": "Optional field-level hint from validation.",
            },
        },
        "usage_examples": [
            {
                "description": "Verify real host identity (argv)",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "execution_kind": "argv",
                    "argv": ["hostname"],
                },
                "explanation": (
                    "Requires host_execution enabled, either ``hostname`` in allowed_commands "
                    "or full_access true, and SSH platzdarm configured. Poll "
                    "terminal_get_status, then terminal_tail."
                ),
            },
            {
                "description": "Chained configured commands in shell mode",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "session_id": _EXAMPLE_SESSION,
                    "execution_kind": "shell",
                    "command": "pytest -q && git status",
                },
                "explanation": (
                    "Both ``pytest`` and ``git`` must be on the allowlist unless full_access "
                    "is true; forbidden patterns in redirects or heredocs still fail "
                    "validation unless full_access is true."
                ),
            },
        ],
        "error_cases": merge_error_cases(
            {
                "HOST_EXECUTION_DISABLED": {
                    "description": (
                        "terminal.host_execution.enabled is false, allowed_commands is empty "
                        "while full_access is false, secrets_path is missing/unsafe, or ssh "
                        "settings are incomplete."
                    ),
                    "message": "HOST_EXECUTION_DISABLED",
                    "solution": (
                        "Enable host_execution, populate allowed_commands or set full_access "
                        "true, configure ssh.target_users, set ssh.known_hosts_path, create "
                        "secrets_path with 0700 or stricter permissions, then restart. Use "
                        "terminal_run for sandbox work."
                    ),
                },
                "HOST_COMMAND_NOT_ALLOWED": {
                    "description": (
                        "Executable basename not in allowed_commands while full_access is "
                        "false, empty argv/command, or invalid chain segment."
                    ),
                    "message": "HOST_COMMAND_NOT_ALLOWED",
                    "solution": (
                        "Add the tool basename to allowed_commands, enable full_access, or "
                        "simplify the command."
                    ),
                },
                "HOST_FORBIDDEN_COMMAND": {
                    "description": (
                        "Forbidden substring or hard-blocked executable (docker, sudo, …)."
                    ),
                    "message": "HOST_FORBIDDEN_COMMAND",
                    "solution": "Remove forbidden syntax or use terminal_run in sandbox.",
                },
                "HOST_KEY_ACCESS_FORBIDDEN": {
                    "description": "Command references the session SSH private key path or key directory.",
                    "message": "HOST_KEY_ACCESS_FORBIDDEN",
                    "solution": "Do not read, copy, or reference session key files in host commands.",
                },
                "TARGET_USER_NOT_ALLOWED": {
                    "description": "target_user is not listed in ssh.target_users.",
                    "message": "TARGET_USER_NOT_ALLOWED",
                    "solution": (
                        "Omit target_user to use the default, or add the user to "
                        "terminal.host_execution.ssh.target_users."
                    ),
                },
                "HOST_SSH_UNREACHABLE": {
                    "description": "SSH connection to the host failed or timed out.",
                    "message": "HOST_SSH_UNREACHABLE",
                    "solution": (
                        "Verify ssh.host/port from the service container, sshd running, "
                        "and network path documented in deployment."
                    ),
                },
                "HOST_HOST_KEY_MISMATCH": {
                    "description": "Host key does not match ssh.known_hosts_path.",
                    "message": "HOST_HOST_KEY_MISMATCH",
                    "solution": "Update known_hosts with the correct host key; never disable StrictHostKeyChecking.",
                },
                "INVALID_SESSION": {
                    "description": "No session directory for (project_id, session_id).",
                    "message": "INVALID_SESSION",
                    "solution": "Call terminal_session_create before terminal_host_exec.",
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
            CASMGR_SESSION_ERROR_CASES,
        ),
        "best_practices": [
            "Keep terminal.host_execution.enabled false by default; enable only as an emergency last line.",
            "Set terminal.host_execution.full_access true only on hosts where every MCP caller may run every host command.",
            "Use terminal_run for normal project work inside the Docker sandbox.",
            "Prefer execution_kind argv with an explicit configured executable.",
            "Always terminal_session_create before the first terminal_host_exec for a session.",
            "Never reference session SSH key paths in host commands (key-guard rejects them).",
            "Poll terminal_get_status until completed before reading exit_code.",
            "Verify results on the real host (hostname/uid), not the service or session container.",
            "After changing host_execution in config, restart the term server.",
        ],
    }
