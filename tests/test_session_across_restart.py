"""Bug e27f23f4: sessions must survive a server restart for terminal_run.

The in-memory SessionStore is emptied by a restart while .terminals/<sid>/
survives on disk; terminal_sessions (disk scan) listed the session but
resolve_session (memory-only get_session) returned INVALID_SESSION. The fix
lazily re-adopts on-disk sessions in resolve_session via
SessionStore.adopt_session.
"""

from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from mcp_terminal.commands import session_resolve
from mcp_terminal.errors import ErrorCode
from mcp_terminal.services.session_store import SessionStore


def _make_session_on_disk(project_dir: Path) -> tuple[str, str]:
    """Create a session with one store instance ('before restart')."""
    project_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    store = SessionStore()
    record, created, err, _ = store.ensure_session(
        project_id=project_id,
        session_id=session_id,
        project_dir=project_dir,
        workspace_write=True,
    )
    assert err is None and created and record is not None
    return project_id, session_id


class AdoptSessionAcrossRestartTests(unittest.TestCase):
    def test_fresh_store_adopts_on_disk_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            project_id, session_id = _make_session_on_disk(project_dir)

            fresh = SessionStore()  # simulates the post-restart empty store
            self.assertIsNone(fresh.get_session(project_id, session_id))

            record = fresh.adopt_session(project_id, session_id, project_dir)
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(record.session_id, session_id)
            self.assertEqual(record.project_id, project_id)
            self.assertTrue(record.workspace_write)
            # Adoption is sticky: the plain lookup now succeeds too.
            self.assertIs(fresh.get_session(project_id, session_id), record)

    def test_adopt_session_without_disk_state_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fresh = SessionStore()
            self.assertIsNone(
                fresh.adopt_session(str(uuid.uuid4()), str(uuid.uuid4()), Path(tmp))
            )


class ResolveSessionAcrossRestartTests(unittest.TestCase):
    def test_resolve_session_readopts_instead_of_invalid_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            project_id, session_id = _make_session_on_disk(project_dir)
            fresh = SessionStore()

            resolved = mock.Mock(success=True, project_dir=project_dir)
            with mock.patch.object(
                session_resolve, "get_session_store", return_value=fresh
            ), mock.patch.object(
                session_resolve, "registry_resolve_project", return_value=resolved
            ), mock.patch.object(
                session_resolve, "session_validate_sync", return_value=None
            ), mock.patch.object(
                session_resolve,
                "subordinate_session_get_sync",
                return_value={"parent_session_id": session_id},
            ):
                record, err = session_resolve.resolve_session(project_id, session_id)

            self.assertIsNone(err)
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(record.session_id, session_id)

    def test_resolve_session_still_invalid_when_no_disk_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fresh = SessionStore()
            resolved = mock.Mock(success=True, project_dir=Path(tmp))
            with mock.patch.object(
                session_resolve, "get_session_store", return_value=fresh
            ), mock.patch.object(
                session_resolve, "registry_resolve_project", return_value=resolved
            ):
                record, err = session_resolve.resolve_session(
                    str(uuid.uuid4()), str(uuid.uuid4())
                )
            self.assertIsNone(record)
            self.assertEqual(err, ErrorCode.INVALID_SESSION)


if __name__ == "__main__":
    unittest.main()
