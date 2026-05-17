"""Session store composite key and single-writer-per-project rules."""

from __future__ import annotations

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

    rec_a, created_a, err_a = store.ensure_session(
        project_id=project_id,
        session_id=session_a,
        project_dir=tmp_path,
        workspace_write=True,
    )
    assert err_a is None and created_a is True
    assert rec_a is not None and rec_a.workspace_write is True

    rec_b, created_b, err_b = store.ensure_session(
        project_id=project_id,
        session_id=session_b,
        project_dir=tmp_path,
        workspace_write=False,
    )
    assert err_b is None and created_b is True
    assert rec_b is not None and rec_b.workspace_write is False

    rec_a2, created_a2, _ = store.ensure_session(
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
