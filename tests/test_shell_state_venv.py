"""Shell state venv session defaults."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from mcp_terminal.services.shell_state import (
    initial_shell_state_for_project,
    read_shell_state,
    resolve_use_venv,
    write_shell_state,
)


def test_initial_shell_state_respects_use_venv_flag() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        state = initial_shell_state_for_project(project, use_venv=True)
        session_dir = project / ".terminals" / "s1"
        write_shell_state(session_dir, state)
        loaded = read_shell_state(session_dir)
        assert loaded.use_venv is True


def test_resolve_use_venv_session_default_when_run_omits_param() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        session_dir = Path(tmp)
        write_shell_state(
            session_dir,
            initial_shell_state_for_project(Path(tmp), use_venv=False),
        )
        assert resolve_use_venv(session_dir, None) is False
        assert resolve_use_venv(session_dir, True) is True


def test_shell_state_json_roundtrip_use_venv() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        session_dir = Path(tmp)
        write_shell_state(
            session_dir,
            initial_shell_state_for_project(Path(tmp), use_venv=True),
        )
        raw = json.loads((session_dir / "shell_state.json").read_text())
        assert raw["use_venv"] is True
