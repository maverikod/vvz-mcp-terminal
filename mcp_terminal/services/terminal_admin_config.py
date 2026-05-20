"""
Terminal admin flags from ``terminal.admin`` (purge-sessions, etc.).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def get_terminal_admin_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return the ``terminal.admin`` object (possibly empty)."""
    if config is None:
        try:
            from mcp_proxy_adapter.config import get_config

            raw = getattr(get_config(), "config_data", None)
            config = raw if isinstance(raw, dict) else {}
        except Exception:  # noqa: BLE001
            config = {}
    terminal = config.get("terminal")
    if not isinstance(terminal, dict):
        return {}
    admin = terminal.get("admin")
    return admin if isinstance(admin, dict) else {}


def purge_sessions_allowed(config: Optional[Dict[str, Any]] = None) -> bool:
    """True when ``terminal.admin.allow_purge_sessions`` is explicitly true."""
    admin = get_terminal_admin_config(config)
    return admin.get("allow_purge_sessions") is True
