"""
Write a full term server JSON config (adapter defaults + terminal overlay).

Used by ``termgr create-config`` and ``mcp-terminal-config generate``.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_terminal.config.config_generator import generate_terminal_config
from mcp_terminal.paths import repo_root
from mcp_terminal.term_config import _DEFAULTS_PATH, default_config_path


def build_term_server_config(**generate_kwargs: Any) -> Dict[str, Any]:
    """Build a validated term server config dict."""
    data: Dict[str, Any] = json.loads(_DEFAULTS_PATH.read_text(encoding="utf-8"))
    reg = data.setdefault("registration", {})
    if not isinstance(reg, dict):
        reg = {}
        data["registration"] = reg
    reg["instance_uuid"] = str(uuid.uuid4())
    return generate_terminal_config(data, **generate_kwargs)


def write_term_server_config(
    path: Path,
    *,
    generate_kwargs: Optional[Dict[str, Any]] = None,
) -> Path:
    """Write config JSON to ``path`` (parent dirs created). Returns resolved path."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = build_term_server_config(**(generate_kwargs or {}))
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def resolve_config_output_path(config_name: str) -> Path:
    """Map CLI config name to ``configs/<name>`` under repo root."""
    name = (config_name or "term_server.json").strip()
    if not name:
        name = "term_server.json"
    if "/" in name or name.startswith("."):
        return Path(name).expanduser().resolve()
    return (repo_root() / "configs" / name).resolve()


def default_create_config_name() -> str:
    """Default filename for ``termgr create-config`` (``configs/`` relative)."""
    return default_config_path().name
