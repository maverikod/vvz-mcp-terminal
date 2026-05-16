"""
Session store for mcp_terminal terminal sessions (C-004, C-005).

Sessions are keyed by ``(project_id, session_id)`` — both external UUID4 values.
At most one session per project may hold workspace write (``workspace_write``).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from mcp_terminal.services.shell_state import ShellState, write_shell_state
from mcp_terminal.services.session_container import stop_session_container

SessionKey = Tuple[str, str]


@dataclass
class SessionRecord:
    """Mutable runtime record for one TerminalSession (C-004)."""

    session_id: str
    project_id: str
    project_dir: Path
    session_dir: Path
    created_at: datetime
    last_activity_at: datetime
    status: str = "idle"
    workspace_write: bool = False
    """When True, this session may mount /workspace read-write for its project."""


class SessionStore:
    """Manages terminal sessions keyed by (project_id, session_id)."""

    TERMINALS_DIR: str = ".terminals"

    def __init__(self) -> None:
        self._sessions: Dict[SessionKey, SessionRecord] = {}
        self._project_writer: Dict[str, str] = {}
        self._logger = logging.getLogger(__name__)

    @staticmethod
    def _key(project_id: str, session_id: str) -> SessionKey:
        return (project_id, session_id)

    def get_session(self, project_id: str, session_id: str) -> Optional[SessionRecord]:
        """Return the session for the composite key, or None."""
        return self._sessions.get(self._key(project_id, session_id))

    def ensure_session(
        self,
        *,
        project_id: str,
        session_id: str,
        project_dir: Path,
    ) -> Tuple[Optional[SessionRecord], bool, Optional[str]]:
        """Create or adopt a session. Returns (record, created, error_code)."""
        key = self._key(project_id, session_id)
        existing = self._sessions.get(key)
        if existing is not None:
            return existing, False, None

        terminals_root = project_dir / self.TERMINALS_DIR
        session_dir = terminals_root / session_id
        self._reconcile_project_writer(project_dir, project_id)

        if session_dir.is_dir():
            rec, err = self._adopt_from_disk(
                project_id=project_id,
                session_id=session_id,
                project_dir=project_dir,
                session_dir=session_dir,
            )
            if err is not None:
                return None, False, err
            assert rec is not None
            self._sessions[key] = rec
            return rec, False, None

        rec = self._create_new(
            project_id=project_id,
            session_id=session_id,
            project_dir=project_dir,
            session_dir=session_dir,
            terminals_root=terminals_root,
        )
        self._sessions[key] = rec
        return rec, True, None

    def _create_new(
        self,
        *,
        project_id: str,
        session_id: str,
        project_dir: Path,
        session_dir: Path,
        terminals_root: Path,
    ) -> SessionRecord:
        terminals_root.mkdir(parents=True, exist_ok=True)
        session_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_gitignore(project_dir)
        now = datetime.now(timezone.utc)
        workspace_write = self._workspace_write_for(project_id, session_id)
        record = SessionRecord(
            session_id=session_id,
            project_id=project_id,
            project_dir=project_dir,
            session_dir=session_dir,
            created_at=now,
            last_activity_at=now,
            workspace_write=workspace_write,
        )
        self._write_session_json(record)
        write_shell_state(session_dir, ShellState())
        self._logger.info(
            "Created session %s for project %s (workspace_write=%s)",
            session_id,
            project_id,
            workspace_write,
        )
        return record

    def _adopt_from_disk(
        self,
        *,
        project_id: str,
        session_id: str,
        project_dir: Path,
        session_dir: Path,
    ) -> Tuple[Optional[SessionRecord], Optional[str]]:
        meta_path = session_dir / "session.json"
        if not meta_path.is_file():
            return None, "SESSION_STATE_CORRUPT"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None, "SESSION_STATE_CORRUPT"
        if not isinstance(meta, dict):
            return None, "SESSION_STATE_CORRUPT"
        stored_pid = str(meta.get("project_id", ""))
        stored_sid = str(meta.get("session_id", ""))
        if stored_pid and stored_pid != project_id:
            return None, "SESSION_PROJECT_MISMATCH"
        if stored_sid and stored_sid != session_id:
            return None, "SESSION_PROJECT_MISMATCH"
        created_raw = meta.get("created_at")
        try:
            created_at = datetime.fromisoformat(created_raw) if created_raw else None
        except (TypeError, ValueError):
            created_at = None
        if created_at is None:
            created_at = datetime.now(timezone.utc)
        workspace_write = self._workspace_write_for(project_id, session_id)
        record = SessionRecord(
            session_id=session_id,
            project_id=project_id,
            project_dir=project_dir,
            session_dir=session_dir,
            created_at=created_at,
            last_activity_at=datetime.now(timezone.utc),
            status=str(meta.get("status", "idle")),
            workspace_write=workspace_write,
        )
        self._write_session_json(record)
        self._logger.info(
            "Adopted session %s for project %s from disk (workspace_write=%s)",
            session_id,
            project_id,
            workspace_write,
        )
        return record, None

    def _reconcile_project_writer(self, project_dir: Path, project_id: str) -> None:
        """Restore per-project write lock from ``session.json`` on disk (after restart)."""
        if project_id in self._project_writer:
            return
        terminals = project_dir / self.TERMINALS_DIR
        if not terminals.is_dir():
            return
        writers: List[Tuple[str, datetime]] = []
        for sub in terminals.iterdir():
            if not sub.is_dir():
                continue
            meta_path = sub / "session.json"
            if not meta_path.is_file():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(meta, dict) or meta.get("project_id") != project_id:
                continue
            if meta.get("workspace_write") is not True:
                continue
            sid = str(meta.get("session_id", sub.name))
            created_raw = meta.get("created_at")
            try:
                created_at = (
                    datetime.fromisoformat(created_raw)
                    if isinstance(created_raw, str)
                    else datetime.now(timezone.utc)
                )
            except ValueError:
                created_at = datetime.now(timezone.utc)
            writers.append((sid, created_at))
        if not writers:
            return
        writers.sort(key=lambda item: item[1])
        self._project_writer[project_id] = writers[0][0]

    def _workspace_write_for(self, project_id: str, session_id: str) -> bool:
        current = self._project_writer.get(project_id)
        if current is None:
            self._project_writer[project_id] = session_id
            return True
        return current == session_id

    def _release_writer(self, project_id: str, session_id: str) -> None:
        if self._project_writer.get(project_id) == session_id:
            del self._project_writer[project_id]

    def _write_session_json(self, record: SessionRecord) -> None:
        meta = {
            "session_id": record.session_id,
            "project_id": record.project_id,
            "created_at": record.created_at.isoformat(),
            "last_activity_at": record.last_activity_at.isoformat(),
            "status": record.status,
            "workspace_write": record.workspace_write,
        }
        (record.session_dir / "session.json").write_text(
            json.dumps(meta, indent=2),
            encoding="utf-8",
        )

    def _ensure_gitignore(self, project_dir: Path) -> None:
        gitignore = project_dir / ".gitignore"
        gi_lines = [f"/{self.TERMINALS_DIR}/\n", "/.mcp_terminal/\n"]
        existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        with gitignore.open("a", encoding="utf-8") as fh:
            for gi_line in gi_lines:
                if gi_line.strip() not in existing:
                    fh.write(gi_line)
                    existing += gi_line

    def touch_activity(self, project_id: str, session_id: str) -> None:
        record = self.get_session(project_id, session_id)
        if record:
            record.last_activity_at = datetime.now(timezone.utc)

    def delete_session(
        self,
        project_id: str,
        session_id: str,
        *,
        force: bool = False,
    ) -> bool:
        key = self._key(project_id, session_id)
        record = self._sessions.get(key)
        if record is None:
            return True
        if record.status == "running" and not force:
            self._logger.warning(
                "Refused to delete running session %s/%s (force=False)",
                project_id,
                session_id,
            )
            return False
        if record.workspace_write:
            self._release_writer(project_id, session_id)
        stop_session_container(project_id, session_id)
        if record.session_dir.exists():
            import shutil

            shutil.rmtree(record.session_dir, ignore_errors=True)
        del self._sessions[key]
        self._logger.info("Deleted session %s for project %s", session_id, project_id)
        return True

    def list_sessions(self, project_id: str) -> List[SessionRecord]:
        return [r for r in self._sessions.values() if r.project_id == project_id]
