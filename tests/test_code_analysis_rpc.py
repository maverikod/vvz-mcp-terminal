"""Tests for code_analysis_rpc helpers."""

from __future__ import annotations

import asyncio

import pytest

from mcp_terminal.code_analysis_rpc import (
    CodeAnalysisRpcError,
    _rpc_error_code,
    _rpc_error_message,
    run_coro_sync,
    unwrap_rpc_success,
)


def test_unwrap_rpc_success_nested_error_code() -> None:
    inner = {
        "success": False,
        "error": {
            "code": "SUBORDINATE_SESSION_ALREADY_EXISTS",
            "message": "duplicate link",
        },
    }
    with pytest.raises(CodeAnalysisRpcError) as exc_info:
        unwrap_rpc_success(inner, command="subordinate_session_create")
    assert exc_info.value.code == "SUBORDINATE_SESSION_ALREADY_EXISTS"
    assert exc_info.value.message == "duplicate link"


def test_rpc_error_helpers_flat_shape() -> None:
    inner = {"success": False, "error": "SESSION_NOT_FOUND", "message": "missing"}
    assert _rpc_error_code(inner) == "SESSION_NOT_FOUND"
    assert _rpc_error_message(inner) == "missing"


def test_run_coro_sync_from_running_loop() -> None:
    async def sample() -> str:
        return "ok"

    async def caller() -> str:
        return str(run_coro_sync(sample()))

    assert asyncio.run(caller()) == "ok"
