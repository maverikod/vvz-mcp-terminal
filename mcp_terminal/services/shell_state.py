"""
Per-session shell state persisted on disk (cwd, optional running container id).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

SHELL_STATE_FILE = "shell_state.json"
_STATE_VERSION = 1
_CWD_RE = re.compile(r"^[a-zA-Z0-9._/-]+$")


@dataclass
class ShellState:
    """Persisted shell session state for one terminal session."""

    cwd: str = "."
    container_id: Optional[str] = None
    container_name: Optional[str] = None
    spec_fingerprint: Optional[str] = None


def normalize_cwd(cwd: str) -> str:
    """Normalize a project-relative cwd (no leading slash, no ..)."""
    value = (cwd or ".").strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    if value in ("", "."):
        return "."
    if value.startswith("/") or ".." in value.split("/"):
        raise ValueError("cwd must be relative and must not contain ..")
    if not _CWD_RE.match(value):
        raise ValueError("cwd contains invalid characters")
    return value


def read_shell_state(session_dir: Path) -> ShellState:
    """Load shell state from ``session_dir/shell_state.json`` or return defaults."""
    path = session_dir / SHELL_STATE_FILE
    if not path.is_file():
        return ShellState()
    try:
        raw: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ShellState()
    if not isinstance(raw, dict):
        return ShellState()
    cwd_raw = str(raw.get("cwd", "."))
    try:
        cwd = normalize_cwd(cwd_raw)
    except ValueError:
        cwd = "."
    cid = raw.get("container_id")
    cname = raw.get("container_name")
    fp = raw.get("spec_fingerprint")
    return ShellState(
        cwd=cwd,
        container_id=str(cid) if cid else None,
        container_name=str(cname) if cname else None,
        spec_fingerprint=str(fp) if fp else None,
    )


def write_shell_state(session_dir: Path, state: ShellState) -> None:
    """Persist shell state atomically (best-effort) under the session directory."""
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _STATE_VERSION,
        "cwd": normalize_cwd(state.cwd),
        "container_id": state.container_id,
        "container_name": state.container_name,
        "spec_fingerprint": state.spec_fingerprint,
    }
    path = session_dir / SHELL_STATE_FILE
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def resolve_cwd(
    session_dir: Path,
    request_cwd: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(effective_cwd, error_code)`` using request override or saved state."""
    if request_cwd is not None:
        try:
            return normalize_cwd(str(request_cwd)), None
        except ValueError:
            return None, "INVALID_CWD"
    state = read_shell_state(session_dir)
    return state.cwd, None


def clear_container_from_state(session_dir: Path) -> None:
    """Remove running-container fields from shell state (container already stopped)."""
    state = read_shell_state(session_dir)
    if not state.container_id and not state.container_name:
        return
    write_shell_state(
        session_dir,
        ShellState(
            cwd=state.cwd,
            spec_fingerprint=None,
        ),
    )
