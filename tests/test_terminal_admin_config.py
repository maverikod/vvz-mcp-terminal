"""Tests for ``terminal.admin`` config and purge gating."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from mcp_terminal.config.config_validator import validate_terminal_config
from mcp_terminal.config.create_config import build_term_server_config
from mcp_terminal.services.terminal_admin_config import purge_sessions_allowed


def test_validate_terminal_admin_allow_purge_must_be_bool() -> None:
    cfg = {
        "terminal": {
            "sessions": {"ttl_seconds": 3600},
            "admin": {"allow_purge_sessions": "yes"},
        }
    }
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "terminal.admin.allow_purge_sessions" in fields


def test_validate_terminal_admin_rejects_non_object() -> None:
    cfg = {"terminal": {"sessions": {"ttl_seconds": 3600}, "admin": []}}
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "terminal.admin" in fields


def test_purge_sessions_allowed_only_when_true() -> None:
    assert not purge_sessions_allowed({})
    assert not purge_sessions_allowed({"terminal": {}})
    assert not purge_sessions_allowed({"terminal": {"admin": {}}})
    assert not purge_sessions_allowed({"terminal": {"admin": {"allow_purge_sessions": False}}})
    assert purge_sessions_allowed(
        {"terminal": {"admin": {"allow_purge_sessions": True}}}
    )


def test_build_term_server_config_includes_terminal_admin_default() -> None:
    cfg = build_term_server_config()
    assert cfg["terminal"]["admin"]["allow_purge_sessions"] is True


def test_build_term_server_config_cli_override_admin_purge_off() -> None:
    cfg = build_term_server_config(terminal_admin_allow_purge_sessions=False)
    assert cfg["terminal"]["admin"]["allow_purge_sessions"] is False


def test_terminal_purge_sessions_mcp_disabled() -> None:
    from mcp_terminal.commands.terminal_purge_sessions_command import (
        TerminalPurgeSessionsCommand,
    )
    from mcp_terminal.errors import ErrorCode

    async def _run() -> None:
        with patch(
            "mcp_terminal.commands.terminal_purge_sessions_command.purge_sessions_allowed",
            return_value=False,
        ):
            r = await TerminalPurgeSessionsCommand().execute(dry_run=True)
            assert r.success is False
            assert r.error == ErrorCode.PURGE_SESSIONS_DISABLED

    asyncio.run(_run())


def test_cmd_purge_sessions_exit_2_when_disabled(tmp_path: Path) -> None:
    from argparse import Namespace

    from mcp_terminal.cli_sessions_purge import cmd_purge_sessions

    cfg = tmp_path / "term_server.json"
    cfg.write_text(
        json.dumps(
            {
                "watch_dirs": {"directories": []},
                "terminal": {
                    "sessions": {"ttl_seconds": 3600},
                    "admin": {"allow_purge_sessions": False},
                },
            }
        ),
        encoding="utf-8",
    )
    args = Namespace(
        config=cfg,
        dry_run=False,
        no_kill_docker=True,
        remove_runtime=False,
    )
    assert cmd_purge_sessions(args) == 2
