"""Shared ``terminal.host_execution`` shape for generator and validator."""

from __future__ import annotations

from typing import Any, Dict

DEFAULT_HOST_EXECUTION_SECRETS_PATH = "/var/mcp-terminal/secrets"

HOST_EXECUTION_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "allowed_commands": [],
    "forbidden_executables_override": None,
    "secrets_path": DEFAULT_HOST_EXECUTION_SECRETS_PATH,
    "ssh": {
        "host": "127.0.0.1",
        "port": 22,
        "target_users": ["mcp-terminal-host"],
        "known_hosts_path": "/etc/mcp-terminal/ssh_known_hosts",
        "connect_timeout": 10,
        "key_manager_script": "/usr/lib/mcp-terminal/manage-session-keys.sh",
    },
}

HOST_EXECUTION_EMPTY_ALLOWLIST_LOG = (
    "terminal.host_execution.enabled is true but allowed_commands is empty; "
    "add command names (e.g. casmgr, git) to terminal.host_execution.allowed_commands "
    "to permit host-side execution"
)

HOST_EXECUTION_SSH_INCOMPLETE_LOG = (
    "terminal.host_execution.enabled is true but ssh configuration is incomplete; "
    "set ssh.target_users (non-empty) and ssh.known_hosts_path"
)

DEFAULT_SSH_KEY_MANAGER_SCRIPT = "/usr/lib/mcp-terminal/manage-session-keys.sh"
DEFAULT_SSH_KNOWN_HOSTS_PATH = "/etc/mcp-terminal/ssh_known_hosts"
