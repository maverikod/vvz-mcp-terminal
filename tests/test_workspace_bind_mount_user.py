"""Tests for container --user matching host workspace ownership."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from mcp_terminal.services.container_runner import workspace_bind_mount_user


def test_workspace_bind_mount_user_matches_directory(tmp_path: Path) -> None:
    st = os.stat(tmp_path)
    assert workspace_bind_mount_user(tmp_path) == f"{st.st_uid}:{st.st_gid}"


@patch("mcp_terminal.services.container_runner.os.stat", side_effect=OSError("boom"))
def test_workspace_bind_mount_user_fallback_on_stat_error(_mock_stat: object) -> None:
    p = Path("/nonexistent_workspace_bind_mount_user_xxx")
    assert workspace_bind_mount_user(p) == "65534:65534"
