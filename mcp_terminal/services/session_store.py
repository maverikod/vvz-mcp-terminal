"""
Session store for mcp_terminal terminal sessions (C-004, C-005).

Manages .terminals/<session_id>/ directories inside project roots.
Enforces TTL tracking and protects running sessions from deletion.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class SessionRecord:
    """Mutable runtime record for one TerminalSession (C-004)."""

    session_id: str
    """UUID4 string."""
    project_id: str
    """Parent project identifier."""
    project_dir: Path
    """Verified canonical host project root."""
    session_dir: Path
    """Absolute path to .terminals/<session_id>/ inside project_dir."""
    created_at: datetime
    """UTC creation timestamp."""
    last_activity_at: datetime
    """UTC timestamp of last activity; updated on any session operation."""
    status: str = "idle"
    """One of: idle, running, expired, deleted."""


class SessionStore:
    """Manages terminal session directories (C-005).

    Thread-safety: callers must ensure no concurrent create/delete on the
    same session_id. The internal dict is not protected by a lock in MVP.
    """

    TERMINALS_DIR: str = ".terminals"  # relative name inside project dir

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionRecord] = {}
        self._logger = logging.getLogger(__name__)

    def create_session(
        self,
        *,
        project_id: str,
        project_dir: Path,
    ) -> SessionRecord:
        """Create a new terminal session directory and register the session.

        Creates .terminals/<session_id>/ inside project_dir. Adds .terminals/
        to .gitignore if not already present.

        Args:
            project_id: Verified project identifier.
            project_dir: Verified canonical host project root path.

        Returns:
            New SessionRecord with status='idle'.
        """
        sid = str(uuid.uuid4())
        terminals_root = project_dir / self.TERMINALS_DIR
        terminals_root.mkdir(exist_ok=True)
        session_dir = terminals_root / sid
        session_dir.mkdir()
        # Ensure .gitignore
        gitignore = project_dir / ".gitignore"
        gi_lines = [f"/{self.TERMINALS_DIR}/\n", "/.mcp_terminal/\n"]
        existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        with gitignore.open("a", encoding="utf-8") as fh:
            for gi_line in gi_lines:
                if gi_line.strip() not in existing:
                    fh.write(gi_line)
                    existing += gi_line
        now = datetime.now(timezone.utc)
        record = SessionRecord(
            session_id=sid,
            project_id=project_id,
            project_dir=project_dir,
            session_dir=session_dir,
            created_at=now,
            last_activity_at=now,
        )
        self._sessions[sid] = record
        # Write session metadata
        meta = {
            "session_id": sid,
            "project_id": project_id,
            "created_at": now.isoformat(),
            "last_activity_at": now.isoformat(),
            "status": "idle",
        }
        (session_dir / "session.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        self._logger.info("Created session %s for project %s", sid, project_id)
        return record

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        """Return the SessionRecord for session_id, or None if not found."""
        return self._sessions.get(session_id)

    def touch_activity(self, session_id: str) -> None:
        """Update last_activity_at for the given session to now (UTC).

        Call after every session operation to keep TTL accurate.
        """
        record = self._sessions.get(session_id)
        if record:
            record.last_activity_at = datetime.now(timezone.utc)

    def delete_session(
        self,
        session_id: str,
        *,
        force: bool = False,
    ) -> bool:
        """Delete a session directory and remove the session from the registry.

        Running sessions (status='running') are rejected unless force=True.

        Args:
            session_id: Session to delete.
            force: When True, delete even if status is 'running'.

        Returns:
            True on success, False when the session is running and force=False.
        """
        record = self._sessions.get(session_id)
        if record is None:
            return True  # already gone
        if record.status == "running" and not force:
            self._logger.warning("Refused to delete running session %s (force=False)", session_id)
            return False
        if record.session_dir.exists():
            import shutil

            shutil.rmtree(record.session_dir, ignore_errors=True)
        del self._sessions[session_id]
        self._logger.info("Deleted session %s", session_id)
        return True

    def list_sessions(self, project_id: str) -> List[SessionRecord]:
        """Return all SessionRecords for the given project_id."""
        return [r for r in self._sessions.values() if r.project_id == project_id]
