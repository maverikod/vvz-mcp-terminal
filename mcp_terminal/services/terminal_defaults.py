"""
Session/run defaults from term server config (``terminal.defaults``).

When MCP parameters are omitted, ``terminal_session_create`` and ``terminal_run``
use these values. Falls back to built-in defaults when the section is missing.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from mcp_terminal.config.terminal_defaults_schema import TERMINAL_DEFAULTS_CONFIG
from mcp_terminal.services.pid_namespace import PID_NAMESPACE_CONTAINER, PID_NAMESPACE_HOST


@dataclass(frozen=True)
class TerminalDefaults:
    """Resolved terminal.defaults from server config."""

    workspace_write: bool
    pid_namespace: str
    keep_container: bool
    use_venv: bool


def _config_data() -> Dict[str, Any]:
    try:
        from mcp_proxy_adapter.config import get_config

        data = getattr(get_config(), "config_data", None)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _defaults_section() -> Dict[str, Any]:
    terminal = _config_data().get("terminal")
    if not isinstance(terminal, dict):
        return {}
    raw = terminal.get("defaults")
    if not isinstance(raw, dict):
        return {}
    return raw


def get_terminal_defaults() -> TerminalDefaults:
    """Return merged terminal.defaults (config + built-in fallbacks)."""
    section = _defaults_section()

    ws = section.get("workspace_write", TERMINAL_DEFAULTS_CONFIG["workspace_write"])
    if not isinstance(ws, bool):
        ws = bool(TERMINAL_DEFAULTS_CONFIG["workspace_write"])

    pid_raw = section.get("pid_namespace", TERMINAL_DEFAULTS_CONFIG["pid_namespace"])
    pid = str(pid_raw).strip().lower()
    if pid not in (PID_NAMESPACE_CONTAINER, PID_NAMESPACE_HOST):
        pid = str(TERMINAL_DEFAULTS_CONFIG["pid_namespace"])

    kc = section.get("keep_container", TERMINAL_DEFAULTS_CONFIG["keep_container"])
    if not isinstance(kc, bool):
        kc = bool(TERMINAL_DEFAULTS_CONFIG["keep_container"])

    uv = section.get("use_venv", TERMINAL_DEFAULTS_CONFIG["use_venv"])
    if not isinstance(uv, bool):
        uv = bool(TERMINAL_DEFAULTS_CONFIG["use_venv"])

    return TerminalDefaults(
        workspace_write=ws, pid_namespace=pid, keep_container=kc, use_venv=uv
    )


def resolve_default_pid_namespace() -> str:
    return get_terminal_defaults().pid_namespace


def resolve_default_keep_container() -> bool:
    return get_terminal_defaults().keep_container


def resolve_default_use_venv() -> bool:
    return get_terminal_defaults().use_venv


def resolve_run_mode(
    *,
    session_workspace_write: bool,
    request_mode: Optional[str] = None,
) -> str:
    """Default mount mode when ``terminal_run`` omits ``mode``.

    Writer sessions mount /workspace read-write; others read-only.
    """
    if request_mode is not None and str(request_mode).strip():
        return str(request_mode).strip()
    return "workspace_write" if session_workspace_write else "read_only"


def resolve_default_workspace_write() -> bool:
    """Default ``workspace_write`` when ``terminal_session_create`` omits the parameter."""
    return get_terminal_defaults().workspace_write
