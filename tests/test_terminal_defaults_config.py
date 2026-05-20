"""terminal.defaults config, generator, and session create behavior."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from mcp_terminal.config.config_generator import generate_terminal_config
from mcp_terminal.config.config_validator import validate_terminal_config
from mcp_terminal.config.create_config import build_term_server_config
from mcp_terminal.services.session_store import SessionStore
from mcp_terminal.services.terminal_defaults import (
    get_terminal_defaults,
    resolve_default_keep_container,
    resolve_default_pid_namespace,
    resolve_default_use_venv,
    resolve_run_mode,
    resolve_default_workspace_write,
)


def test_resolve_run_mode_matches_session_write_capability() -> None:
    assert resolve_run_mode(session_workspace_write=True) == "workspace_write"
    assert resolve_run_mode(session_workspace_write=False) == "read_only"
    assert resolve_run_mode(session_workspace_write=False, request_mode="scratch_write") == (
        "scratch_write"
    )


def test_generator_includes_terminal_defaults() -> None:
    cfg = generate_terminal_config({})
    assert cfg["terminal"]["defaults"]["workspace_write"] is True
    assert cfg["terminal"]["defaults"]["pid_namespace"] == "host"
    assert cfg["terminal"]["defaults"]["keep_container"] is True
    assert cfg["terminal"]["defaults"]["use_venv"] is True
    assert "pid_namespace" not in cfg["runtime"]
    assert validate_terminal_config(cfg) == []


def test_validator_rejects_bad_terminal_defaults() -> None:
    cfg = generate_terminal_config({})
    cfg["terminal"]["defaults"]["pid_namespace"] = "pod"
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "terminal.defaults.pid_namespace" in fields


def test_build_term_server_config_has_terminal_section() -> None:
    cfg = build_term_server_config()
    assert "terminal" in cfg
    assert "defaults" in cfg["terminal"]


def test_session_create_persists_api_or_config_defaults(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    store = SessionStore()
    rec, created, err, _ = store.ensure_session(
        project_id="00000000-0000-4000-8000-000000000001",
        session_id="00000000-0000-4000-8000-000000000002",
        project_dir=project_dir,
        workspace_write=True,
        use_venv=True,
        pid_namespace="host",
    )
    assert err is None and created and rec is not None
    assert rec.workspace_write is True
    assert rec.pid_namespace == "host"
    meta = json.loads((rec.session_dir / "session.json").read_text(encoding="utf-8"))
    assert meta["workspace_write"] is True and meta["pid_namespace"] == "host"
    state = json.loads((rec.session_dir / "shell_state.json").read_text(encoding="utf-8"))
    assert state["use_venv"] is True


def test_terminal_defaults_from_config_data() -> None:
    fake = {
        "terminal": {
            "defaults": {
                "workspace_write": False,
                "pid_namespace": "container",
                "keep_container": True,
            }
        }
    }
    with patch("mcp_terminal.services.terminal_defaults._config_data", return_value=fake):
        td = get_terminal_defaults()
        assert td.workspace_write is False
        assert td.pid_namespace == "container"
        assert td.keep_container is True
        assert resolve_default_pid_namespace() == "container"
        assert resolve_default_keep_container() is True
        assert resolve_default_use_venv() is True
        assert resolve_default_workspace_write() is False
