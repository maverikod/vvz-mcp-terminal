"""Tests for code_analysis_sessions RPC wrappers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mcp_terminal.code_analysis_rpc import CodeAnalysisRpcError
from mcp_terminal.code_analysis_sessions import (
    subordinate_session_create_sync,
    subordinate_session_delete_sync,
    subordinate_session_get_sync,
)


_APP_CONFIG = {
    "code_analysis": {
        "host": "127.0.0.1",
        "port": 15000,
        "protocol": "https",
        "timeout_seconds": 30,
        "ssl": {"cert": "c", "key": "k", "ca": "a"},
    },
    "registration": {"instance_uuid": "00000000-0000-4000-8000-000000000099"},
}


def test_subordinate_session_create_idempotent_on_duplicate() -> None:
    with patch(
        "mcp_terminal.code_analysis_sessions.call_code_analysis_sync",
        side_effect=CodeAnalysisRpcError("SUBORDINATE_SESSION_ALREADY_EXISTS", "dup"),
    ):
        out = subordinate_session_create_sync(
            _APP_CONFIG,
            parent_session_id="00000000-0000-4000-8000-000000000001",
        )
    assert out.get("already_exists") is True


def test_subordinate_session_get_returns_none_when_missing() -> None:
    with patch(
        "mcp_terminal.code_analysis_sessions.call_code_analysis_sync",
        side_effect=CodeAnalysisRpcError("SUBORDINATE_SESSION_NOT_FOUND", "missing"),
    ):
        assert (
            subordinate_session_get_sync(
                _APP_CONFIG,
                parent_session_id="00000000-0000-4000-8000-000000000001",
            )
            is None
        )


def test_subordinate_session_delete_ignores_missing() -> None:
    with patch(
        "mcp_terminal.code_analysis_sessions.call_code_analysis_sync",
        side_effect=CodeAnalysisRpcError("SUBORDINATE_SESSION_NOT_FOUND", "missing"),
    ):
        subordinate_session_delete_sync(
            _APP_CONFIG,
            parent_session_id="00000000-0000-4000-8000-000000000001",
        )


def test_subordinate_session_create_propagates_other_errors() -> None:
    with patch(
        "mcp_terminal.code_analysis_sessions.call_code_analysis_sync",
        side_effect=CodeAnalysisRpcError("RPC_ERROR", "boom"),
    ):
        with pytest.raises(CodeAnalysisRpcError):
            subordinate_session_create_sync(
                _APP_CONFIG,
                parent_session_id="00000000-0000-4000-8000-000000000001",
            )
