"""Sessionless host execution run storage."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from mcp_terminal.paths import data_dir

HOST_EXEC_PROJECT_ID = "host"
HOST_EXEC_RUN_PREFIX = "host-"
HOST_EXEC_SCOPE = "host_exec"


@dataclass(frozen=True)
class HostExecRun:
    """Directory-backed host execution run reference."""

    run_id: str
    run_dir: Path


def host_exec_root() -> Path:
    """Return the root directory for sessionless host execution output."""
    return data_dir() / "host_exec" / "runs"


def create_host_exec_run() -> HostExecRun:
    """Create and return a fresh sessionless host execution run directory."""
    root = host_exec_root()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    run_id = f"{HOST_EXEC_RUN_PREFIX}{uuid.uuid4()}"
    run_dir = root / run_id
    run_dir.mkdir(mode=0o700)
    return HostExecRun(run_id=run_id, run_dir=run_dir)


def resolve_host_exec_run(run_id: str) -> HostExecRun | None:
    """Resolve a host_run_id to its directory, enforcing containment."""
    clean = str(run_id or "").strip()
    if not clean.startswith(HOST_EXEC_RUN_PREFIX):
        return None
    root = host_exec_root()
    run_dir = root / clean
    try:
        run_dir.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    if not run_dir.is_dir():
        return None
    return HostExecRun(run_id=clean, run_dir=run_dir)
