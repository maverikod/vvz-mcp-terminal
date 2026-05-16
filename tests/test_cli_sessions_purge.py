"""Tests for termgr purge-sessions CLI helpers."""

from __future__ import annotations

import json
from pathlib import Path

from mcp_terminal.cli_sessions_purge import discover_terminals_dirs, purge_all_terminal_sessions


def test_discover_and_purge_session_dirs(tmp_path: Path) -> None:
    anchor = tmp_path / "tools"
    anchor.mkdir()
    proj = anchor / "myproj"
    proj.mkdir()
    (proj / "projectid").write_text(
        json.dumps({"id": "00000000-0000-4000-8000-000000000001", "description": "x"}),
        encoding="utf-8",
    )
    sess_root = proj / ".terminals"
    sess = sess_root / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    sess.mkdir(parents=True)
    (sess / "session.json").write_text("{}", encoding="utf-8")

    cfg = tmp_path / "term_server.json"
    cfg.write_text(
        json.dumps({"watch_dirs": {"directories": [str(anchor)]}}),
        encoding="utf-8",
    )
    found = discover_terminals_dirs(cfg)
    assert len(found) == 1 and found[0] == sess_root.resolve()

    report = purge_all_terminal_sessions(
        cfg,
        dry_run=False,
        kill_docker=False,
        remove_runtime=False,
    )
    assert report.session_dirs_removed == 1
    assert not sess.exists()
    assert not sess_root.exists()
