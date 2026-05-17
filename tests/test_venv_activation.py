"""Tests for automatic .venv activation in exec scripts."""

from __future__ import annotations

import tempfile
from pathlib import Path

from mcp_terminal.services.session_container import _write_exec_script
from mcp_terminal.services.venv_activation import (
    WORKSPACE_VENV_ROOT,
    venv_activation_shell_block,
)


def test_venv_block_empty_when_disabled() -> None:
    assert venv_activation_shell_block(use_venv=False) == ""


def test_venv_block_uses_absolute_workspace_path() -> None:
    block = venv_activation_shell_block(use_venv=True)
    assert f"{WORKSPACE_VENV_ROOT}/bin" in block
    assert "VIRTUAL_ENV" in block
    assert "activate" not in block


def test_exec_script_includes_venv_by_default() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        session_dir = Path(tmp)
        path = _write_exec_script(
            session_dir,
            "000001",
            effective_cwd="tests",
            execution_kind="shell",
            command="casmgr status",
            argv=None,
            use_venv=True,
        )
        script = path.read_text(encoding="utf-8")
        assert "/workspace/.venv/bin" in script
        assert "VIRTUAL_ENV" in script
        assert "activate" not in script
        assert "casmgr status" in script
        assert script.index("VIRTUAL_ENV") < script.index("casmgr status")


def test_exec_script_skips_venv_when_disabled() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        session_dir = Path(tmp)
        path = _write_exec_script(
            session_dir,
            "000002",
            effective_cwd=".",
            execution_kind="shell",
            command="python3 --version",
            argv=None,
            use_venv=False,
        )
        script = path.read_text(encoding="utf-8")
        assert "/workspace/.venv/bin/activate" not in script
