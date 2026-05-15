"""
Background refresh of ``ProjectRegistry`` from config and Code Analysis roots.

Runs in a daemon thread: periodically re-merges anchor directories, rebuilds the
registry, and swaps it under the same lock used by ``registry_resolve_project``.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable, Dict

from mcp_terminal.runtime_context import set_project_registry
from mcp_terminal.services.project_registry import ProjectRegistry
from mcp_terminal.services.project_roots import merged_project_anchor_dirs

logger = logging.getLogger(__name__)


def rebuild_project_registry(app_config: Dict[str, Any], *, config_path: Path) -> ProjectRegistry:
    """Build a new registry from the merged anchor directory list."""
    roots = merged_project_anchor_dirs(app_config, config_path=config_path)
    reg = ProjectRegistry(roots)
    reg.build()
    return reg


def start_project_registry_refresh_daemon(
    config_path: Path,
    interval_seconds: float,
    get_app_config: Callable[[], Dict[str, Any]],
) -> threading.Event:
    """Start a daemon thread that periodically rebuilds and installs the registry.

    Args:
        config_path: Path to ``term_server.json`` (for Code Analysis client TLS).
        interval_seconds: Sleep between refresh cycles; must be positive.
        get_app_config: Returns current merged app config (e.g. ``get_config().config_data``).

    Returns:
        ``threading.Event``; set it to request the loop to exit after the current sleep.
    """
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")

    stop = threading.Event()

    def _loop() -> None:
        while not stop.wait(interval_seconds):
            try:
                snap = get_app_config()
                if not isinstance(snap, dict):
                    snap = {}
                reg = rebuild_project_registry(snap, config_path=config_path)
                set_project_registry(reg)
                logger.debug(
                    "Project registry refreshed (%s anchor(s), %s project id(s))",
                    len(reg.root_dirs),
                    len(reg.known_project_ids),
                )
            except Exception:  # noqa: BLE001
                logger.exception("Project registry background refresh failed")

    thread = threading.Thread(
        target=_loop,
        name="mcp_terminal_project_registry_refresh",
        daemon=True,
    )
    thread.start()
    return stop
