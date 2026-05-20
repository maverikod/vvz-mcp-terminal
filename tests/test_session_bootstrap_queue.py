"""Tests for queued session bootstrap on terminal_session_create."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import asyncio
from typing import Any
from unittest.mock import patch

from mcp_terminal.commands.terminal_session_create_command import TerminalSessionCreateCommand
from mcp_terminal.runtime_context import set_terminal_services
from mcp_terminal.services.session_bootstrap import read_bootstrap_state, write_bootstrap_pending
from mcp_terminal.services.session_store import SessionStore


def _mock_enqueue_coroutine(coro: Any, *, job_id: str) -> str:
    if asyncio.iscoroutine(coro):
        coro.close()
    return job_id


@dataclass
class _FakeResolution:
    success: bool
    project_dir: Path | None
    error_code: str | None = None


@patch("mcp_terminal.commands.terminal_session_create_command.enqueue_coroutine")
@patch("mcp_terminal.commands.terminal_session_create_command.registry_resolve_project")
def test_session_create_enqueues_bootstrap(
    mock_resolve,
    mock_enqueue,
    tmp_path: Path,
) -> None:
    mock_enqueue.side_effect = lambda coro: _mock_enqueue_coroutine(
        coro, job_id="bootstrap-job-abc"
    )
    project_id = "00000000-0000-4000-8000-000000000001"
    session_id = "00000000-0000-4000-8000-000000000002"
    mock_resolve.return_value = _FakeResolution(success=True, project_dir=tmp_path)
    store = SessionStore()
    set_terminal_services(session_store=store, project_registry=object())  # type: ignore[arg-type]

    cmd = TerminalSessionCreateCommand()
    result = asyncio.run(
        cmd.execute(
            project_id=project_id,
            session_id=session_id,
            bootstrap_python_env=True,
        )
    )
    assert result.success is True
    assert result.data is not None
    assert result.data["bootstrap"]["status"] == "pending"
    assert result.data["bootstrap"]["job_id"] == "bootstrap-job-abc"
    mock_enqueue.assert_called_once()

    assert result.data["session_id"] == session_id
    rec = store.get_session(project_id, session_id)
    assert rec is not None
    state = read_bootstrap_state(rec.session_dir)
    assert state is not None
    assert state["runtime_image"]["status"] == "pending"
    assert state["runtime_image"]["job_id"] == "bootstrap-job-abc"


def test_write_bootstrap_pending(tmp_path: Path) -> None:
    sess = tmp_path / "sess"
    sess.mkdir()
    write_bootstrap_pending(sess, job_id="j-1")
    data = json.loads((sess / "bootstrap.json").read_text(encoding="utf-8"))
    assert data["runtime_image"]["status"] == "pending"
    assert data["runtime_image"]["job_id"] == "j-1"
