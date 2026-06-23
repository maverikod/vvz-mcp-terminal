"""Input schema for ``terminal_host_exec``."""

from __future__ import annotations

from typing import Any, Dict

from mcp_terminal.commands.schema_common import schema_project_id, schema_session_id

_DEFAULT_TIMEOUT_S = 600


def get_terminal_host_exec_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "project_id": schema_project_id(),
            "session_id": schema_session_id(),
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
                    "Optional project-relative working directory on the host project tree. "
                    "Omitted: use shell_state.json from the previous run."
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
        "required": ["project_id", "session_id", "execution_kind"],
        "additionalProperties": False,
    }
