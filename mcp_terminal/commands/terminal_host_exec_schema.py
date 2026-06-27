"""Input schema for ``terminal_host_exec``."""

from __future__ import annotations

from typing import Any, Dict

_DEFAULT_TIMEOUT_S = 600


def get_terminal_host_exec_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "Optional legacy project id. If set, session_id is required.",
            },
            "session_id": {
                "type": "string",
                "description": "Optional legacy terminal session id. If omitted, host_run_id is used.",
            },
            "execution_kind": {
                "type": "string",
                "enum": ["shell", "argv"],
                "description": "shell: command string. argv: explicit argument vector.",
            },
            "command": {
                "type": "string",
                "description": "Shell command when execution_kind is shell.",
            },
            "argv": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Argv list when execution_kind is argv.",
            },
            "target_user": {
                "type": "string",
                "description": (
                    "SSH login on the real host. Must be listed in "
                    "terminal.host_execution.ssh.target_users. "
                    "Omitted: first target_users entry."
                ),
            },
            "cwd": {
                "type": "string",
                "description": (
                    "Sessionless mode: absolute host working directory, default /root. "
                    "Legacy session mode: project-relative working directory."
                ),
            },
            "timeout_seconds": {
                "type": "integer",
                "default": _DEFAULT_TIMEOUT_S,
                "minimum": 1,
                "maximum": 86400,
                "description": "Max seconds before the remote host process is killed.",
            },
            "use_venv": {
                "type": "boolean",
                "description": (
                    "When omitted, uses session default from shell_state.json. "
                    "When true, prepends project/.venv/bin to PATH on the host."
                ),
            },
        },
        "required": ["execution_kind"],
        "additionalProperties": False,
    }
