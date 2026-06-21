"""Tests for shell_state.json persistence."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mcp_terminal.services.shell_state import (
    read_shell_state,
    resolve_cwd,
    write_shell_state,
    ShellState,
    normalize_cwd,
)


def test_normalize_cwd() -> None:
    assert normalize_cwd(".") == "."
    assert normalize_cwd("./tests") == "tests"
    with pytest.raises(ValueError):
        normalize_cwd("/abs")
    with pytest.raises(ValueError):
        normalize_cwd("../x")


def test_read_write_roundtrip(tmp_path: Path) -> None:
    write_shell_state(
        tmp_path,
        ShellState(cwd="src/pkg", container_name="mcp-term-abc", spec_fingerprint="fp1"),
    )
    state = read_shell_state(tmp_path)
    assert state.cwd == "src/pkg"
    assert state.container_name == "mcp-term-abc"
    assert state.spec_fingerprint == "fp1"


def test_resolve_cwd_override(tmp_path: Path) -> None:
    write_shell_state(tmp_path, ShellState(cwd="a"))
    cwd, err = resolve_cwd(tmp_path, "b")
    assert err is None and cwd == "b"
    cwd2, err2 = resolve_cwd(tmp_path, None)
    assert err2 is None and cwd2 == "a"


def test_write_shell_state_chowns_to_session_dir_owner(tmp_path: Path) -> None:
    if os.geteuid() != 0:
        pytest.skip("chown requires root")
    owner = tmp_path / "owner"
    owner.mkdir()
    os.chown(owner, os.getuid(), os.getgid())
    session_dir = owner / ".terminals" / "sess"
    session_dir.mkdir(parents=True)
    os.chown(session_dir, owner.stat().st_uid, owner.stat().st_gid)
    write_shell_state(session_dir, ShellState(cwd="."))
    state_file = session_dir / "shell_state.json"
    assert state_file.is_file()
    assert state_file.stat().st_uid == owner.stat().st_uid
    assert state_file.stat().st_gid == owner.stat().st_gid
