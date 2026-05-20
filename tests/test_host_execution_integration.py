"""Host execution integration tests (tech_spec §28.9): H-5, H-10."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from mcp_terminal.commands.terminal_run_command import TerminalRunCommand
from mcp_terminal.errors import ErrorCode
from mcp_terminal.services.command_history import CommandHistory
from mcp_terminal.services.host_execution_config import (
    HostCommandValidation,
    HostExecutionConfig,
)
from mcp_terminal.services.host_run_service import enqueue_host_terminal_run
from mcp_terminal.services.shell_state import ShellState, write_shell_state


def _mock_enqueue_coroutine(coro: Any, *, job_id: str = "mock-job") -> str:
    """Close coroutine passed to patched enqueue_coroutine (avoids RuntimeWarning)."""
    if asyncio.iscoroutine(coro):
        coro.close()
    return job_id


_HE_CFG = HostExecutionConfig(
    enabled=True, allowed_commands=frozenset({"pytest", "git", "true", "sleep"})
)


def _patch_host_config(cfg: HostExecutionConfig):
    return patch(
        "mcp_terminal.services.host_execution_config.get_host_execution_config",
        return_value=cfg,
    )


async def _enqueue_sandbox_mock(
    *,
    project_dir: Path,
    session_dir: Path,
    project_id: str,
    session_id: str,
) -> int:
    """Run terminal_run enqueue path with mocked TerminalExecutionJob (no Docker)."""
    write_shell_state(session_dir, ShellState(cwd=".", use_venv=False))
    srec = SimpleNamespace(
        session_dir=session_dir,
        workspace_write=False,
        pid_namespace="container",
    )
    resolved = SimpleNamespace(success=True, project_dir=project_dir, error_code=None)
    session_store = SimpleNamespace(touch_activity=lambda *_a, **_k: None)

    cmd = TerminalRunCommand()
    with (
        patch(
            "mcp_terminal.commands.terminal_run_command.registry_resolve_project",
            return_value=resolved,
        ),
        patch(
            "mcp_terminal.commands.terminal_run_command.resolve_session",
            return_value=(srec, None),
        ),
        patch(
            "mcp_terminal.commands.terminal_run_command.get_session_store",
            return_value=session_store,
        ),
        patch(
            "mcp_terminal.commands.terminal_run_command.resolve_execution_image",
            return_value=("mcp-terminal:test", None),
        ),
        patch(
            "mcp_terminal.commands.terminal_run_command.TerminalExecutionJob",
            return_value=MagicMock(),
        ) as mock_job_cls,
        patch(
            "mcp_terminal.commands.terminal_run_command.enqueue_coroutine",
            side_effect=lambda coro: _mock_enqueue_coroutine(coro, job_id="sandbox-job"),
        ),
    ):
        result = await cmd.execute(
            project_id=project_id,
            session_id=session_id,
            execution_kind="argv",
            argv=["true"],
            use_venv=False,
        )

    assert result.success is True
    assert result.data is not None
    mock_job_cls.assert_called_once()
    return int(result.data["seq"])


async def _enqueue_host_mock(
    *,
    project_dir: Path,
    session_dir: Path,
    project_id: str,
    session_id: str,
) -> int:
    """Run terminal_run_host enqueue path with mocked job queue (no host spawn)."""
    srec = SimpleNamespace(session_dir=session_dir)
    session_store = SimpleNamespace(touch_activity=lambda *_a, **_k: None)

    with (
        _patch_host_config(_HE_CFG),
        patch(
            "mcp_terminal.services.host_run_service.validate_host_run_request",
            return_value=HostCommandValidation(ok=True),
        ),
        patch(
            "mcp_terminal.services.host_run_service.enqueue_coroutine",
            side_effect=lambda coro: _mock_enqueue_coroutine(coro, job_id="host-job"),
        ),
    ):
        result = await enqueue_host_terminal_run(
            project_id=project_id,
            session_id=session_id,
            srec=srec,
            execution_kind="argv",
            cmd_str=None,
            argv_list=["true"],
            effective_cwd=".",
            timeout_seconds=30,
            use_venv=False,
            project_dir=project_dir,
            session_store=session_store,
        )

    assert result.success is True
    assert result.data is not None
    return int(result.data["seq"])


def test_h10_sandbox_and_host_share_monotonic_seq(tmp_path: Path) -> None:
    """H-10: sandbox and host enqueue share monotonic seq in one session."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    project_id = "00000000-0000-4000-8000-000000000001"
    session_id = "00000000-0000-4000-8000-000000000002"

    sandbox_seq1 = asyncio.run(
        _enqueue_sandbox_mock(
            project_dir=project_dir,
            session_dir=session_dir,
            project_id=project_id,
            session_id=session_id,
        )
    )
    host_seq = asyncio.run(
        _enqueue_host_mock(
            project_dir=project_dir,
            session_dir=session_dir,
            project_id=project_id,
            session_id=session_id,
        )
    )
    sandbox_seq2 = asyncio.run(
        _enqueue_sandbox_mock(
            project_dir=project_dir,
            session_dir=session_dir,
            project_id=project_id,
            session_id=session_id,
        )
    )

    seqs = []
    for line in (session_dir / "history.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            seqs.append(json.loads(line)["seq"])

    assert sandbox_seq1 == 1
    assert host_seq == 2
    assert sandbox_seq2 == 3
    assert seqs == [1, 2, 3]

    history = CommandHistory(session_dir)
    assert history.allocate_seq() == 4


# H-5 docker forbidden despite allowlist (validation layer): see tests/test_host_shell_scanner.py
# and tests/test_host_invariants.py::test_h5_docker_path_manipulation_still_forbidden


def test_h5_docker_enqueue_rejected_without_queueing(tmp_path: Path) -> None:
    """H-5: enqueue_host_terminal_run rejects docker without queueing a host job."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    srec = SimpleNamespace(session_dir=session_dir)
    session_store = SimpleNamespace(touch_activity=lambda *_a, **_k: None)
    cfg = HostExecutionConfig(enabled=True, allowed_commands=frozenset({"docker", "pytest"}))

    async def _run() -> None:
        with (
            _patch_host_config(cfg),
            patch("mcp_terminal.services.host_run_service.enqueue_coroutine") as mock_enqueue,
        ):
            result = await enqueue_host_terminal_run(
                project_id="00000000-0000-4000-8000-000000000001",
                session_id="00000000-0000-4000-8000-000000000002",
                srec=srec,
                execution_kind="argv",
                cmd_str=None,
                argv_list=["docker", "ps"],
                effective_cwd=".",
                timeout_seconds=30,
                use_venv=False,
                project_dir=project_dir,
                session_store=session_store,
            )
        assert result.success is False
        assert result.error == ErrorCode.HOST_FORBIDDEN_COMMAND
        mock_enqueue.assert_not_called()
        assert not (session_dir / "history.jsonl").exists()

    asyncio.run(_run())
