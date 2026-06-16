"""
Repository and install path resolution (runtime cwd-independent).

When ``MCP_TERMINAL_CONFIG_DIR`` / ``MCP_TERMINAL_LOG_DIR`` / ``MCP_TERMINAL_DATA_DIR``
are set (Debian package / Docker host integration), paths follow FHS layout under
``/etc/mcp-terminal``, ``/var/log/mcp-terminal``, and ``/var/mcp-terminal``.
Otherwise dev layout uses the git checkout root.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Return absolute path to repository root (parent of ``mcp_terminal`` package)."""
    return Path(__file__).resolve().parent.parent


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def is_packaged_layout() -> bool:
    """True when FHS install env vars are set (``.deb`` / production container)."""
    return _env_path("MCP_TERMINAL_CONFIG_DIR") is not None


def config_dir() -> Path:
    """Directory containing ``term_server.json`` (``configs/`` or ``/etc/mcp-terminal``)."""
    env = _env_path("MCP_TERMINAL_CONFIG_DIR")
    if env is not None:
        return env
    return repo_root() / "configs"


def log_dir() -> Path:
    """Server log directory (``logs/`` under repo or ``/var/log/mcp-terminal``)."""
    env = _env_path("MCP_TERMINAL_LOG_DIR")
    if env is not None:
        return env
    return repo_root() / "logs"


def data_dir() -> Path:
    """Application data root (repo root in dev, ``/var/mcp-terminal`` when packaged)."""
    env = _env_path("MCP_TERMINAL_DATA_DIR")
    if env is not None:
        return env
    return repo_root()


def state_dir() -> Path:
    """Package state directory (``/var/lib/mcp-terminal`` when packaged)."""
    env = _env_path("MCP_TERMINAL_STATE_DIR")
    if env is not None:
        return env
    return log_dir()


def mtls_dir() -> Path:
    """TLS certificate tree (``mtls_certificates/`` or ``/etc/mcp-terminal/mtls_certificates``)."""
    env = _env_path("MCP_TERMINAL_MTLS_DIR")
    if env is not None:
        return env
    return repo_root() / "mtls_certificates"


def default_term_server_config_path() -> Path:
    """Path to the runtime SimpleConfig JSON."""
    return config_dir() / "term_server.json"
