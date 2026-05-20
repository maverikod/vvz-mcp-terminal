"""Tests for TtlCleanupService (G-005)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from mcp_terminal.services.session_store import SessionRecord, SessionStore
from mcp_terminal.services.ttl_cleanup import TtlCleanupService


def test_ttl_cleanup_start_stop() -> None:
    """Service background thread starts and stops cleanly."""
    store = SessionStore()
    svc = TtlCleanupService(store, ttl_seconds=3600, cleanup_interval_seconds=3600)
    svc.start()
    assert svc._thread is not None
    assert svc._thread.is_alive()
    svc.stop()
    assert svc._thread is not None
    assert not svc._thread.is_alive()


def test_ttl_cleanup_calls_session_store_delete() -> None:
    """One cleanup pass invokes SessionStore.delete_session for expired sessions."""
    store = MagicMock()
    old = datetime.now(timezone.utc) - timedelta(seconds=7200)
    record = SessionRecord(
        session_id="00000000-0000-4000-8000-000000000099",
        project_id="00000000-0000-4000-8000-000000000001",
        project_dir=Path("/tmp/proj"),
        session_dir=Path("/tmp/proj/.terminals/s"),
        created_at=old,
        last_activity_at=old,
        status="idle",
    )
    store._sessions = {record.session_id: record}
    store.delete_session = MagicMock(return_value=True)

    svc = TtlCleanupService(
        store,
        ttl_seconds=60,
        cleanup_interval_seconds=3600,
        delete_expired=True,
        delete_running=False,
    )
    svc._cleanup_once()

    store.delete_session.assert_called_once_with(
        record.project_id,
        record.session_id,
        force=False,
    )


def test_ttl_cleanup_skips_running_without_force() -> None:
    """Running sessions are not deleted unless delete_running is enabled."""
    store = MagicMock()
    old = datetime.now(timezone.utc) - timedelta(seconds=7200)
    record = SimpleNamespace(
        session_id="s-run",
        project_id="p",
        last_activity_at=old,
        status="running",
    )
    store._sessions = {"s-run": record}
    store.delete_session = MagicMock(return_value=True)

    svc = TtlCleanupService(
        store,
        ttl_seconds=60,
        cleanup_interval_seconds=3600,
        delete_expired=True,
        delete_running=False,
    )
    svc._cleanup_once()

    store.delete_session.assert_not_called()
