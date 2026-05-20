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
from typing import Any, Dict, List, Optional, Tuple

from mcp_terminal.services.shell_state import (
    initial_shell_state_for_project,
    write_shell_state,
)
from mcp_terminal.services.pid_namespace import (
    PID_NAMESPACE_CONTAINER,
    normalize_pid_namespace,
)
from mcp_terminal.services.terminal_defaults import (
    resolve_default_pid_namespace,
    resolve_default_use_venv,
    resolve_default_workspace_write,
)
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
    pid_namespace: str = PID_NAMESPACE_CONTAINER
    """Docker PID mode: ``container`` (default) or ``host`` (``--pid=host``)."""


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
        use_venv: Optional[bool] = None,
        pid_namespace: Optional[str] = None,
        workspace_write: Optional[bool] = None,
    ) -> Tuple[Optional[SessionRecord], bool, Optional[str], Optional[Dict[str, Any]]]:
        """Create or adopt a session.

        Returns ``(record, created, error_code, error_data)``. ``error_data`` is non-None
        only for some errors (e.g. ``WORKSPACE_WRITE_NOT_ALLOWED`` includes the holder
        ``session_id``).
        """
        key = self._key(project_id, session_id)
        existing = self._sessions.get(key)
        if existing is not None:
            if existing.session_dir.is_dir():
                return existing, False, None, None
            self._logger.info(
                "Dropping in-memory session %s (missing session_dir after purge or manual delete)",
                session_id,
            )
            if existing.workspace_write:
                self._release_writer(project_id, session_id)
            del self._sessions[key]

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
                return None, False, err, None
            assert rec is not None
            self._sessions[key] = rec
            return rec, False, None, None

        rec, create_err, create_err_data = self._create_new(
            project_id=project_id,
            session_id=session_id,
            project_dir=project_dir,
            session_dir=session_dir,
            terminals_root=terminals_root,
            use_venv=use_venv,
            pid_namespace=pid_namespace,
            workspace_write=workspace_write,
        )
        if create_err is not None:
            return None, False, create_err, create_err_data
        assert rec is not None
        self._sessions[key] = rec
        return rec, True, None, None

    def _create_new(
        self,
        *,
        project_id: str,
        session_id: str,
        project_dir: Path,
        session_dir: Path,
        terminals_root: Path,
        use_venv: Optional[bool] = None,
        pid_namespace: Optional[str] = None,
        workspace_write: Optional[bool] = None,
    ) -> Tuple[Optional[SessionRecord], Optional[str], Optional[Dict[str, Any]]]:
        terminals_root.mkdir(parents=True, exist_ok=True)
        self._ensure_gitignore(project_dir)
        now = datetime.now(timezone.utc)

        wants_write = (
            workspace_write
            if workspace_write is not None
            else resolve_default_workspace_write()
        )
        if wants_write:
            current = self._project_writer.get(project_id)
            if current is not None and current != session_id:
                return (
                    None,
                    "WORKSPACE_WRITE_NOT_ALLOWED",
                    {"workspace_writer_session_id": current},
                )
            self._project_writer[project_id] = session_id
            ws_on_disk = True
        else:
            ws_on_disk = False

        session_dir.mkdir(parents=True, exist_ok=True)

        if pid_namespace is None:
            pid_ns = normalize_pid_namespace(None, default=resolve_default_pid_namespace())
        else:
            pid_ns = normalize_pid_namespace(pid_namespace)

        venv_on = use_venv if use_venv is not None else resolve_default_use_venv()

        record = SessionRecord(
            session_id=session_id,
            project_id=project_id,
            project_dir=project_dir,
            session_dir=session_dir,
            created_at=now,
            last_activity_at=now,
            workspace_write=ws_on_disk,
            pid_namespace=pid_ns,
        )
        self._write_session_json(record)
        write_shell_state(
            session_dir,
            initial_shell_state_for_project(project_dir, use_venv=venv_on),
        )
        self._logger.info(
            "Created session %s for project %s (workspace_write=%s use_venv=%s pid_namespace=%s)",
            session_id,
            project_id,
            ws_on_disk,
            venv_on,
            pid_ns,
        )
        return record, None, None

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
        ws_raw = meta.get("workspace_write")
        if isinstance(ws_raw, bool):
            workspace_write = ws_raw
        else:
            workspace_write = False
        if workspace_write:
            self._project_writer[project_id] = session_id
        stored_pid_ns = meta.get("pid_namespace")
        if stored_pid_ns is None:
            pid_ns = normalize_pid_namespace(None, default=resolve_default_pid_namespace())
        else:
            pid_ns = normalize_pid_namespace(stored_pid_ns)
        record = SessionRecord(
            session_id=session_id,
            project_id=project_id,
            project_dir=project_dir,
            session_dir=session_dir,
            created_at=created_at,
            last_activity_at=datetime.now(timezone.utc),
            status=str(meta.get("status", "idle")),
            workspace_write=workspace_write,
            pid_namespace=pid_ns,
        )
        self._write_session_json(record)
        self._logger.info(
            "Adopted session %s for project %s from disk (workspace_write=%s)",
            session_id,
            project_id,
            workspace_write,
        )
        return record, None

    @staticmethod
    def _workspace_writer_claim_valid(
        terminals_root: Path, project_id: str, writer_session_id: str
    ) -> bool:
        """True when on-disk session still claims workspace write for this project."""
        meta_path = terminals_root / writer_session_id / "session.json"
        if not meta_path.is_file():
            return False
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(meta, dict):
            return False
        if meta.get("project_id") != project_id:
            return False
        return meta.get("workspace_write") is True

    def _reconcile_project_writer(self, project_dir: Path, project_id: str) -> None:
        """Restore per-project write lock from ``session.json`` on disk (after restart)."""
        terminals = project_dir / self.TERMINALS_DIR
        current_sid = self._project_writer.get(project_id)
        if current_sid is not None and not self._workspace_writer_claim_valid(
            terminals, project_id, current_sid
        ):
            del self._project_writer[project_id]
            self._logger.info(
                "Cleared stale workspace writer lock for project %s (was %s)",
                project_id,
                current_sid,
            )

        if project_id in self._project_writer:
            return
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
            "pid_namespace": record.pid_namespace,
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

    def persist_session_record(self, record: SessionRecord) -> None:
        """Rewrite ``session.json`` and refresh in-memory entry."""
        key = self._key(record.project_id, record.session_id)
        self._sessions[key] = record
        self._write_session_json(record)

    def touch_activity(self, project_id: str, session_id: str) -> None:
        record = self.get_session(project_id, session_id)
        if record:
            record.last_activity_at = datetime.now(timezone.utc)

    def delete_session_by_id(
        self,
        project_id: str,
        session_id: str,
        project_dir: Path,
        *,
        force: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """Remove session from memory and/or ``.terminals/<session_id>/`` on disk.

        Returns ``(ok, error_code)``. ``error_code`` is ``SESSION_RUNNING`` when delete
        is refused for a running in-memory session and ``force`` is false.
        """
        key = self._key(project_id, session_id)
        record = self._sessions.get(key)
        if record is not None:
            ok = self.delete_session(project_id, session_id, force=force)
            return ok, (None if ok else "SESSION_RUNNING")

        session_dir = (project_dir / self.TERMINALS_DIR / session_id).resolve()
        if not session_dir.is_dir():
            return True, None

        meta_path = session_dir / "session.json"
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(meta, dict) and meta.get("workspace_write") is True:
                    if self._project_writer.get(project_id) == session_id:
                        self._release_writer(project_id, session_id)
            except (OSError, json.JSONDecodeError):
                pass

        stop_session_container(project_id, session_id)
        import shutil

        shutil.rmtree(session_dir, ignore_errors=True)
        self._logger.info(
            "Deleted on-disk-only session %s for project %s", session_id, project_id
        )
        return True, None

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

    def list_sessions_for_project(
        self, project_id: str, project_dir: Path
    ) -> List[SessionRecord]:
        """In-memory sessions plus any ``.terminals/*`` dirs on disk not yet registered."""
        self._reconcile_project_writer(project_dir, project_id)
        by_id: Dict[str, SessionRecord] = {
            r.session_id: r for r in self._sessions.values() if r.project_id == project_id
        }
        terminals_root = project_dir / self.TERMINALS_DIR
        if not terminals_root.is_dir():
            return list(by_id.values())

        for sub in terminals_root.iterdir():
            if not sub.is_dir():
                continue
            sid = sub.name
            if sid in by_id:
                continue
            rec, err = self._adopt_from_disk(
                project_id=project_id,
                session_id=sid,
                project_dir=project_dir,
                session_dir=sub,
            )
            if err is None and rec is not None:
                by_id[sid] = rec
                self._sessions[self._key(project_id, sid)] = rec
        return list(by_id.values())

    def drop_sessions_for_purged_terminals(self, terminals_roots: List[Path]) -> int:
        """Unregister in-memory sessions under purged ``.terminals`` trees (and ghosts)."""
        normalized = {p.resolve() for p in terminals_roots}
        dropped = 0
        for key in list(self._sessions.keys()):
            rec = self._sessions[key]
            try:
                parent = rec.session_dir.parent.resolve()
            except OSError:
                parent = None
            if (parent is not None and parent in normalized) or not rec.session_dir.is_dir():
                if rec.workspace_write:
                    self._release_writer(rec.project_id, rec.session_id)
                del self._sessions[key]
                dropped += 1
        return dropped
