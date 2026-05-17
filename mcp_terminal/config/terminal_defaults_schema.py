"""Shared ``terminal.defaults`` shape for generator and validator."""

from __future__ import annotations

from typing import Any, Dict

TERMINAL_DEFAULTS_CONFIG: Dict[str, Any] = {
    "workspace_write": True,
    "pid_namespace": "host",
    "keep_container": True,
    "use_venv": True,
}
