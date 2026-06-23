"""Tests for project ownership helpers (host_run_identity)."""

from __future__ import annotations

import os
from pathlib import Path

from mcp_terminal.services.host_run_identity import (
    prepare_path_for_project_owner_access,
    project_owner_ids,
    project_owner_user_spec,
)


def test_project_owner_ids_match_stat(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    uid, gid = project_owner_ids(project)
    st = os.stat(project)
    assert uid == st.st_uid
    assert gid == st.st_gid


def test_project_owner_user_spec(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    spec = project_owner_user_spec(project)
    assert ":" in spec


def test_prepare_path_for_project_owner_access_noop_without_root(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    target = tmp_path / "terminals"
    prepare_path_for_project_owner_access(project, target)
    assert target.is_dir()
