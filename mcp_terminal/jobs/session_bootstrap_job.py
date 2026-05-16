"""
SessionBootstrapJob: queue job for per-project runtime image build on session open (C-005).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from mcp_terminal.services.session_bootstrap import run_session_runtime_bootstrap


@dataclass(frozen=True)
class SessionBootstrapJobParams:
    """Immutable parameters for one SessionBootstrapJob invocation."""

    project_id: str
    session_id: str
    project_dir: Path
    session_dir: Path
    image_profile: str
    timeout_seconds: int


class SessionBootstrapJob:
    """Queue job that runs ``run_session_runtime_bootstrap`` in a worker thread."""

    def __init__(self, params: SessionBootstrapJobParams) -> None:
        self._params = params
        self._logger = logging.getLogger(__name__)

    def run(self) -> dict:
        """Build or verify runtime image; session is kept on failure (stock image still usable)."""
        p = self._params
        br = run_session_runtime_bootstrap(
            p.project_dir,
            project_id=p.project_id,
            session_dir=p.session_dir,
            image_profile=p.image_profile,
            timeout_seconds=p.timeout_seconds,
        )
        if not br.success:
            self._logger.warning(
                "Bootstrap failed for session %s: %s",
                p.session_id,
                br.detail[:500],
            )
        return {
            "success": br.success,
            "ran": br.ran,
            "skipped": br.skipped,
            "exit_code": br.exit_code,
            "detail": br.detail,
            "status": "completed" if br.success else "failed",
        }
