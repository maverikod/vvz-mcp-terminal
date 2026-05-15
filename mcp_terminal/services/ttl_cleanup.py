"""
TTL cleanup service for mcp_terminal (C-013, C-005).

Deletes expired terminal sessions according to configured TTL.
Never deletes running sessions unless delete_running_sessions=True.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from mcp_terminal.services.session_store import SessionStore


class TtlCleanupService:
    """Background service that cleans up expired terminal sessions (C-013/C-005)."""

    def __init__(
        self,
        session_store: SessionStore,
        *,
        ttl_seconds: int,
        cleanup_interval_seconds: int = 3600,
        delete_expired: bool = True,
        delete_running: bool = False,
    ) -> None:
        """Initialise the cleanup service.

        Args:
            session_store: SessionStore instance to clean up expired sessions from.
            ttl_seconds: Session TTL in seconds from ConfigOverlay.
            cleanup_interval_seconds: How often to run a cleanup cycle.
            delete_expired: When True, delete expired non-running sessions.
            delete_running: When True, allow deleting running sessions too.
        """
        self._store = session_store
        self._ttl = timedelta(seconds=ttl_seconds)
        self._interval = cleanup_interval_seconds
        self._delete_expired = delete_expired
        self._delete_running = delete_running
        self._logger = logging.getLogger(__name__)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the background cleanup thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ttl-cleanup")
        self._thread.start()
        self._logger.info(
            "TTL cleanup started (interval=%ds, ttl=%ds)",
            self._interval,
            int(self._ttl.total_seconds()),
        )

    def stop(self) -> None:
        """Stop the background cleanup thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        """Background loop: clean up expired sessions on each interval."""
        while not self._stop_event.wait(timeout=self._interval):
            self._cleanup_once()

    def _cleanup_once(self) -> None:
        """Run one cleanup pass over all sessions in the store."""
        now = datetime.now(timezone.utc)
        for record in list(self._store._sessions.values()):
            age = now - record.last_activity_at
            if age < self._ttl:
                continue
            if not self._delete_expired:
                continue
            if record.status == "running" and not self._delete_running:
                self._logger.debug("Skipping running session %s", record.session_id)
                continue
            deleted = self._store.delete_session(record.session_id, force=self._delete_running)
            if deleted:
                self._logger.info(
                    "TTL deleted session %s (age=%.0fs)",
                    record.session_id,
                    age.total_seconds(),
                )
