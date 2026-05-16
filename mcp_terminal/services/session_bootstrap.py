"""
One-shot project runtime Docker image on terminal session open (C-005).

Builds (once per ``requirements.txt`` fingerprint) under ``.mcp_terminal/runtime/``,
writes ``image_state.json`` with ``docker image inspect`` identity for later checks.
``terminal_run`` verifies that identity before using the local tag.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_terminal.services.project_runtime_image import ensure_project_runtime_image

_BOOTSTRAP_JSON = "bootstrap.json"


def write_bootstrap_pending(session_dir: Path, *, job_id: str) -> None:
    """Write ``bootstrap.json`` while the adapter queue job is pending."""
    payload: Dict[str, Any] = {
        "runtime_image": {
            "status": "pending",
            "job_id": job_id,
        }
    }
    (session_dir / _BOOTSTRAP_JSON).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def read_bootstrap_state(session_dir: Path) -> Optional[Dict[str, Any]]:
    """Return parsed ``bootstrap.json`` or None if missing."""
    path = session_dir / _BOOTSTRAP_JSON
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


@dataclass(frozen=True)
class SessionBootstrapResult:
    """Outcome of ``run_session_runtime_bootstrap``."""

    success: bool
    ran: bool
    """True when a ``docker build`` ran (not only verify/skip)."""
    skipped: bool
    """True when no build was needed (no requirements, not Python, or image already ok)."""
    exit_code: int
    """0 on success; non-zero on failure."""
    detail: str
    stderr_tail: str


def run_session_runtime_bootstrap(
    project_dir: Path,
    *,
    project_id: str,
    session_dir: Path,
    image_profile: str = "python_dev_3_12",
    timeout_seconds: int = 1200,
) -> SessionBootstrapResult:
    """Ensure per-project runtime image exists; write ``bootstrap.json`` under session_dir."""
    ok, skipped, code, detail = ensure_project_runtime_image(
        project_dir,
        project_id=project_id,
        image_profile=image_profile,
        build_timeout_seconds=timeout_seconds,
    )
    payload: Dict[str, Any] = {
        "runtime_image": {
            "status": "completed" if ok else "failed",
            "success": ok,
            "skipped_build": skipped,
            "exit_code": code,
            "detail": detail,
        }
    }
    (session_dir / "bootstrap.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    ran = ok and not skipped
    exit_out = 0 if ok else (int(code) if isinstance(code, int) and code != 0 else 1)
    return SessionBootstrapResult(
        success=ok,
        ran=ran,
        skipped=skipped,
        exit_code=exit_out,
        detail=detail,
        stderr_tail="" if ok else detail[-4000:],
    )
