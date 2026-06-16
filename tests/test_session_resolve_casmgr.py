"""Tests for casmgr session gate in session_resolve."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_terminal.code_analysis_rpc import CodeAnalysisRpcError
from mcp_terminal.commands.session_resolve import resolve_session
from mcp_terminal.errors import ErrorCode
from mcp_terminal.runtime_context import set_terminal_services
from mcp_terminal.services.session_store import SessionStore


@pytest.fixture
def session_env(tmp_path: Path) -> tuple[SessionStore, str, str]:
    store = SessionStore()
    set_terminal_services(session_store=store, project_registry=object())  # type: ignore[arg-type]
    project_id = "00000000-0000-4000-8000-000000000001"
    session_id = "00000000-0000-4000-8000-000000000002"
    store.ensure_session(
        project_id=project_id,
        session_id=session_id,
        project_dir=tmp_path,
    )
    return store, project_id, session_id


def _config_mock() -> MagicMock:
    cfg = MagicMock()
    cfg.config_data = {
        "code_analysis": {"host": "127.0.0.1", "port": 15000},
        "registration": {"instance_uuid": "00000000-0000-4000-8000-000000000010"},
    }
    return cfg


def test_resolve_session_rejects_missing_client_session(session_env, tmp_path: Path) -> None:
    _, project_id, session_id = session_env
    with patch(
        "mcp_terminal.commands.session_resolve.get_config",
        return_value=_config_mock(),
    ), patch(
        "mcp_terminal.commands.session_resolve.session_validate_sync",
        side_effect=CodeAnalysisRpcError("SESSION_NOT_FOUND", "missing"),
    ):
        rec, err = resolve_session(project_id, session_id)
    assert rec is None
    assert err == ErrorCode.CLIENT_SESSION_NOT_FOUND


def test_resolve_session_rejects_missing_subordinate_link(session_env) -> None:
    _, project_id, session_id = session_env
    with patch(
        "mcp_terminal.commands.session_resolve.get_config",
        return_value=_config_mock(),
    ), patch(
        "mcp_terminal.commands.session_resolve.session_validate_sync",
        return_value={},
    ), patch(
        "mcp_terminal.commands.session_resolve.subordinate_session_get_sync",
        return_value=None,
    ):
        rec, err = resolve_session(project_id, session_id)
    assert rec is None
    assert err == ErrorCode.SUBORDINATE_SESSION_NOT_LINKED
