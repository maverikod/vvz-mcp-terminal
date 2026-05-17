"""Tests for termgr purge-sessions CLI helpers."""

from __future__ import annotations

import json
from pathlib import Path

from mcp_terminal.cli_sessions_purge import discover_terminals_dirs, purge_all_terminal_sessions
from mcp_terminal.services.terminal_container_purge import (
    is_terminal_sandbox_container,
    remove_all_terminal_containers,
)


def test_is_terminal_sandbox_container() -> None:
    assert is_terminal_sandbox_container(
        image="ghcr.io/mcp-terminal/python-dev:3.12",
        names="jolly_curie",
        session_label="",
    )
    assert is_terminal_sandbox_container(
        image="mcp-terminal:pid-abc123",
        names="x",
        session_label="",
    )
    assert is_terminal_sandbox_container(
        image="python:3.12",
        names="mcp-term-deadbeef01234567",
        session_label="",
    )
    assert is_terminal_sandbox_container(
        image="python:3.12",
        names="x",
        session_label="true",
    )
    assert not is_terminal_sandbox_container(
        image="nginx:latest",
        names="web",
        session_label="",
    )


def test_remove_all_terminal_containers_dry_run(monkeypatch) -> None:
    monkeypatch.setattr(
        "mcp_terminal.services.terminal_container_purge.subprocess.check_output",
        lambda *a, **k: "cid1\tghcr.io/mcp-terminal/python-dev:3.12\tmcp-term-abc\ttrue\ncid2\tnginx\tweb\t\n",
    )

    def _fail(*_a, **_k):
        raise AssertionError("docker rm should not run in dry_run")

    monkeypatch.setattr(
        "mcp_terminal.services.terminal_container_purge.subprocess.run",
        _fail,
    )
    assert remove_all_terminal_containers(dry_run=True) == 1


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


def test_discover_terminals_dirs_code_analysis_unreachable(tmp_path: Path, monkeypatch) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    proj = tools / "proj"
    proj.mkdir()
    sess_root = proj / ".terminals"
    (sess_root / "sess-id").mkdir(parents=True)

    cfg = tmp_path / "term_server.json"
    cfg.write_text(
        json.dumps(
            {
                "watch_dirs": {"directories": [str(tools)]},
                "code_analysis": {"enabled": True, "host": "127.0.0.1", "port": 1},
            }
        ),
        encoding="utf-8",
    )

    def _fail(*_a, **_k):
        raise ValueError("code_analysis list_watch_dirs: connection refused")

    monkeypatch.setattr(
        "mcp_terminal.services.project_roots.list_watch_dirs_sync",
        _fail,
    )

    found = discover_terminals_dirs(cfg)
    assert len(found) == 1 and found[0] == sess_root.resolve()
