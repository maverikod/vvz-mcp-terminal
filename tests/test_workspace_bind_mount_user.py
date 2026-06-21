"""Tests for container --user selection."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from mcp_terminal.services.container_runner import (
    SANDBOX_CONTAINER_USER,
    sandbox_container_user,
    session_container_user,
    writer_session_user,
    workspace_bind_mount_user,
)


def test_sandbox_container_user_is_root() -> None:
    assert sandbox_container_user() == SANDBOX_CONTAINER_USER == "0:0"


def test_writer_session_user_matches_directory(tmp_path: Path) -> None:
    st = os.stat(tmp_path)
    assert writer_session_user(tmp_path) == f"{st.st_uid}:{st.st_gid}"


def test_session_container_user_readonly_uses_root(tmp_path: Path) -> None:
    assert session_container_user(tmp_path, workspace_readonly=True) == "0:0"


def test_session_container_user_writer_uses_owner(tmp_path: Path) -> None:
    st = os.stat(tmp_path)
    assert session_container_user(tmp_path, workspace_readonly=False) == f"{st.st_uid}:{st.st_gid}"


def test_workspace_bind_mount_user_matches_directory(tmp_path: Path) -> None:
    st = os.stat(tmp_path)
    assert workspace_bind_mount_user(tmp_path) == f"{st.st_uid}:{st.st_gid}"


@patch("mcp_terminal.services.container_runner.project_owner_user_spec", return_value="65534:65534")
def test_workspace_bind_mount_user_fallback_on_stat_error(_mock_spec: object) -> None:
    p = Path("/nonexistent_workspace_bind_mount_user_xxx")
    assert workspace_bind_mount_user(p) == "65534:65534"
