"""
Bootstrap mcp_proxy_adapter logging before adapter imports.

CommandRegistry initializes file logging at import time with a hardcoded
``./logs`` directory (relative to ``WORKDIR`` ``/app``). Production containers
run as ``mcp-terminal`` and cannot create ``/app/logs``; logs must go to
``MCP_TERMINAL_LOG_DIR`` (``/var/log/mcp-terminal``).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from pathlib import Path


def ensure_adapter_log_dir() -> None:
    """Ensure adapter file logging target exists before ``mcp_proxy_adapter`` import."""
    from mcp_terminal.paths import is_packaged_layout, log_dir

    target = log_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    if not is_packaged_layout():
        return

    app_logs = Path("/app/logs")
    if app_logs.is_symlink() or app_logs.is_dir():
        return

    # Image should ship /app/logs -> MCP_TERMINAL_LOG_DIR; recreate if missing (dev builds).
    try:
        if os.access("/app", os.W_OK):
            app_logs.symlink_to(target)
    except OSError:
        pass
