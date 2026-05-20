"""Session store composite key and single-writer-per-project rules."""

from __future__ import annotations

import shutil
from pathlib import Path

from mcp_terminal.commands.session_resolve import resolve_session
from mcp_terminal.runtime_context import set_terminal_services
from mcp_terminal.services.session_ids import validate_uuid4_field
from mcp_terminal.services.session_store import SessionStore


def test_ensure_session_composite_key_and_single_writer(tmp_path: Path) -> None:
    store = SessionStore()
    project_id = "00000000-0000-4000-8000-000000000001"
    session_a = "00000000-0000-4000-8000-000000000002"
    session_b = "00000000-0000-4000-8000-000000000003"

    rec_a, created_a, err_a, _ = store.ensure_session(
        project_id=project_id,
        session_id=session_a,
        project_dir=tmp_path,
        workspace_write=True,
    )
    assert err_a is None and created_a is True
    assert rec_a is not None and rec_a.workspace_write is True

    rec_b, created_b, err_b, _ = store.ensure_session(
        project_id=project_id,
        session_id=session_b,
        project_dir=tmp_path,
        workspace_write=False,
    )
    assert err_b is None and created_b is True
    assert rec_b is not None and rec_b.workspace_write is False

    rec_a2, created_a2, _, _ = store.ensure_session(
        project_id=project_id,
        session_id=session_a,
        project_dir=tmp_path,
    )
    assert created_a2 is False and rec_a2 is rec_a

    assert store.get_session(project_id, session_b) is rec_b
    assert store.get_session(project_id, "00000000-0000-4000-8999-000000000099") is None


def test_validate_uuid4_field() -> None:
    assert validate_uuid4_field("not-a-uuid", "session_id") == "INVALID_SESSION_ID"
    assert (
        validate_uuid4_field("00000000-0000-4000-8000-000000000001", "project_id") is None
    )


def test_resolve_session_requires_pair(tmp_path: Path) -> None:
    store = SessionStore()
    set_terminal_services(session_store=store, project_registry=object())  # type: ignore[arg-type]
    project_id = "00000000-0000-4000-8000-000000000001"
    session_id = "00000000-0000-4000-8000-000000000002"
    store.ensure_session(
        project_id=project_id,
        session_id=session_id,
        project_dir=tmp_path,
    )
    rec, err = resolve_session(project_id, session_id)
    assert err is None and rec is not None
    _, missing = resolve_session(project_id, "00000000-0000-4000-8000-000000000099")
    assert missing == "INVALID_SESSION"


def test_second_workspace_writer_rejected_with_holder_id(tmp_path: Path) -> None:
    store = SessionStore()
    project_id = "00000000-0000-4000-8000-000000000010"
    session_a = "00000000-0000-4000-8000-000000000011"
    session_b = "00000000-0000-4000-8000-000000000012"

    _, _, err_a, _ = store.ensure_session(
        project_id=project_id,
        session_id=session_a,
        project_dir=tmp_path,
        workspace_write=True,
    )
    assert err_a is None

    _, _, err_b, data_b = store.ensure_session(
        project_id=project_id,
        session_id=session_b,
        project_dir=tmp_path,
        workspace_write=True,
    )
    assert err_b == "WORKSPACE_WRITE_NOT_ALLOWED"
    assert data_b == {"workspace_writer_session_id": session_a}


def test_stale_workspace_writer_lock_cleared_when_dir_removed(tmp_path: Path) -> None:
    """Simulates disk-only purge: in-memory writer must not block forever."""
    store = SessionStore()
    project_id = "00000000-0000-4000-8000-000000000020"
    session_a = "00000000-0000-4000-8000-000000000021"
    session_b = "00000000-0000-4000-8000-000000000022"

    rec_a, _, err_a, _ = store.ensure_session(
        project_id=project_id,
        session_id=session_a,
        project_dir=tmp_path,
        workspace_write=True,
    )
    assert err_a is None and rec_a is not None
    shutil.rmtree(rec_a.session_dir)

    rec_b, _, err_b, _ = store.ensure_session(
        project_id=project_id,
        session_id=session_b,
        project_dir=tmp_path,
        workspace_write=True,
    )
    assert err_b is None
    assert rec_b is not None and rec_b.workspace_write is True


def test_drop_sessions_for_purged_terminals_clears_ghosts(tmp_path: Path) -> None:
    store = SessionStore()
    project_id = "00000000-0000-4000-8000-000000000030"
    session_a = "00000000-0000-4000-8000-000000000031"

    rec, _, err, _ = store.ensure_session(
        project_id=project_id,
        session_id=session_a,
        project_dir=tmp_path,
        workspace_write=True,
    )
    assert err is None and rec is not None
    terminals_root = tmp_path / SessionStore.TERMINALS_DIR
    shutil.rmtree(rec.session_dir)

    dropped = store.drop_sessions_for_purged_terminals([terminals_root])
    assert dropped == 1
    assert store.get_session(project_id, session_a) is None


def test_ensure_session_recreates_after_purged_disk(tmp_path: Path) -> None:
    store = SessionStore()
    project_id = "00000000-0000-4000-8000-000000000040"
    session_a = "00000000-0000-4000-8000-000000000041"

    rec, created, err, _ = store.ensure_session(
        project_id=project_id,
        session_id=session_a,
        project_dir=tmp_path,
        workspace_write=False,
    )
    assert created and err is None and rec is not None
    shutil.rmtree(rec.session_dir)

    rec2, created2, err2, _ = store.ensure_session(
        project_id=project_id,
        session_id=session_a,
        project_dir=tmp_path,
        workspace_write=False,
    )
    assert err2 is None and created2 is True
    assert rec2 is not None and rec2.session_dir.is_dir()


def test_delete_session_by_id_removes_disk_only(tmp_path: Path) -> None:
    store = SessionStore()
    project_id = "00000000-0000-4000-8000-000000000050"
    session_a = "00000000-0000-4000-8000-000000000051"
    session_dir = tmp_path / SessionStore.TERMINALS_DIR / session_a
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text(
        '{"session_id": "00000000-0000-4000-8000-000000000051", '
        '"project_id": "00000000-0000-4000-8000-000000000050", '
        '"workspace_write": false}',
        encoding="utf-8",
    )

    ok, err = store.delete_session_by_id(project_id, session_a, tmp_path, force=True)
    assert ok and err is None
    assert not session_dir.exists()
