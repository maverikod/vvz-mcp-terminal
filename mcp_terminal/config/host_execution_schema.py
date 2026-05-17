"""Shared ``terminal.host_execution`` shape for generator and validator."""

from __future__ import annotations

from typing import Any, Dict, List

HOST_EXECUTION_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "allowed_commands": [],
}

# Logged at startup when enabled=True and allowlist is empty.
HOST_EXECUTION_EMPTY_ALLOWLIST_LOG = (
    "terminal.host_execution.enabled is true but allowed_commands is empty; "
    "add command names (e.g. casmgr, git) to terminal.host_execution.allowed_commands "
    "to permit host-side execution"
)
