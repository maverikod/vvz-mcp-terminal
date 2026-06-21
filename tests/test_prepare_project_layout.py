"""Tests for prepare_project_layout.py (install-time root helper)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "docker" / "pkg" / "prepare_project_layout.py"
if str(_SCRIPT.parent) not in sys.path:
    sys.path.insert(0, str(_SCRIPT.parent))

from prepare_project_layout import (  # noqa: E402
    _discover_project_dirs,
    prepare_terminals_dir,
)


def test_discover_project_dirs_anchor_and_child(tmp_path: Path) -> None:
    anchor = tmp_path / "watch"
    anchor.mkdir()
    child = anchor / "proj_a"
    child.mkdir()
    (child / "projectid").write_text('{"id":"00000000-0000-4000-8000-000000000001"}', encoding="utf-8")
    (anchor / "projectid").write_text('{"id":"00000000-0000-4000-8000-000000000002"}', encoding="utf-8")

    found = {p.name for p in _discover_project_dirs(anchor)}
    assert found == {"watch", "proj_a"}


@pytest.mark.skipif(os.geteuid() != 0, reason="prepare_terminals_dir chown requires root")
def test_prepare_terminals_dir_sets_project_owner(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    os.chown(project, os.getuid(), os.getgid())

    prepare_terminals_dir(project)
    terminals = project / ".terminals"
    st = terminals.stat()
    assert st.st_uid == project.stat().st_uid
    assert st.st_gid == project.stat().st_gid
    assert stat.S_IMODE(st.st_mode) == 0o2770


@pytest.mark.skipif(os.geteuid() != 0, reason="prepare_project_layout.py requires root")
def test_prepare_from_config_script(tmp_path: Path) -> None:
    watch = tmp_path / "watch"
    project = watch / "app"
    project.mkdir(parents=True)
    (project / "projectid").write_text(
        '{"id":"11111111-1111-4111-8111-111111111111","description":"t"}',
        encoding="utf-8",
    )
    os.chown(project, os.getuid(), os.getgid())

    config = tmp_path / "term_server.json"
    config.write_text(
        json.dumps({"watch_dirs": {"directories": [str(watch)]}}),
        encoding="utf-8",
    )
    proc = subprocess.run(  # noqa: S603
        [sys.executable, str(_SCRIPT), str(config)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    terminals = project / ".terminals"
    assert terminals.is_dir()
    assert stat.S_IMODE(terminals.stat().st_mode) == 0o2770
