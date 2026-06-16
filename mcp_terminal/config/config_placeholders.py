"""
Detect unresolved production config placeholders (Debian package template).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from typing import Any, Final, List, Optional

# Tokens scanned in raw config text (postinst grep uses the same set).
UNRESOLVED_PLACEHOLDER_MARKERS: Final[tuple[str, ...]] = (
    "CHANGE_ME",
    "MCP_PROXY_HOST",
    "REPLACE_ON_INSTALL",
    "CODE_ANALYSIS_HOST",
    "WATCH_DIRS_ROOT",
)


def _try_load_config(text: str) -> Optional[dict[str, Any]]:
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def list_unresolved_placeholder_hints(text: str) -> List[str]:
    """Return human-readable hints for placeholders still present in *text*."""
    hints: List[str] = []
    data = _try_load_config(text)

    if "CHANGE_ME" in text:
        hints.append("server.advertised_host (CHANGE_ME)")
    if "MCP_PROXY_HOST" in text:
        hints.append("registration URLs (MCP_PROXY_HOST)")
    if "REPLACE_ON_INSTALL" in text:
        hints.append("registration.instance_uuid (REPLACE_ON_INSTALL)")
    if "WATCH_DIRS_ROOT" in text:
        hints.append(
            "watch_dirs.directories (WATCH_DIRS_ROOT — bind-mount the same path "
            "via MCP_TERMINAL_EXTRA_BINDS)"
        )

    if "CODE_ANALYSIS_HOST" in text:
        hints.append(
            "code_analysis.host (CODE_ANALYSIS_HOST — casmgr-server; "
            "port 15010 production / 15000 dev checkout)"
        )

    return hints


def config_text_has_unresolved_placeholders(text: str) -> bool:
    """True when *text* still contains install-time placeholder tokens."""
    return bool(list_unresolved_placeholder_hints(text))


def unresolved_placeholders_error_message(*, config_path: str, text: str) -> str:
    """Multi-line error for startup / CLI when placeholders block service start."""
    hints = list_unresolved_placeholder_hints(text)
    lines = [
        "Configuration contains unresolved install placeholders; service cannot start.",
        f"Config file: {config_path}",
    ]
    if hints:
        lines.append("Replace:")
        lines.extend(f"  - {hint}" for hint in hints)
    else:
        lines.append(
            f"Replace tokens: {', '.join(UNRESOLVED_PLACEHOLDER_MARKERS)}"
        )
    lines.append("Then run: sudo mcp-terminal-docker recreate")
    return "\n".join(lines)


def assert_config_placeholders_resolved(*, config_path: str, text: str) -> None:
    """Raise ``ValueError`` when install placeholders remain in config *text*."""
    if not config_text_has_unresolved_placeholders(text):
        return
    raise ValueError(unresolved_placeholders_error_message(config_path=config_path, text=text))
