"""Unit tests for sync_host_sudo_lib (no root required)."""

from __future__ import annotations

import grp
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[1] / "docker" / "pkg"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))
from sync_host_sudo_lib import generate_sudoers_body, resolve_path  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "docker" / "pkg" / "sync-host-sudo.sh"


def test_resolve_path_prefers_command_paths() -> None:
    path = resolve_path("termgr", command_paths={"termgr": "/usr/local/bin/termgr"}, sudo_map={})
    assert path == "/usr/local/bin/termgr"


def test_resolve_path_sudo_override_path() -> None:
    path = resolve_path(
        "casmgr",
        command_paths={},
        sudo_map={"casmgr": {"as_user": "casuser", "path": "/usr/bin/casmgr"}},
    )
    assert path == "/usr/bin/casmgr"


def test_generate_sudoers_includes_root_when_service_user_differs(tmp_path: Path) -> None:
    config = {
        "terminal": {
            "host_execution": {
                "enabled": True,
                "service_user": "mcp-terminal",
                "allowed_commands": ["grep"],
                "run_as": {
                    "command_paths": {"grep": "/usr/bin/grep"},
                },
            }
        }
    }
    cfg_path = tmp_path / "term_server.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")
    body = generate_sudoers_body(cfg_path)
    assert "mcp-terminal ALL=(ALL) NOPASSWD:" in body
    assert "root ALL=(ALL) NOPASSWD:" in body
    assert "Defaults:mcp-terminal !use_pty" in body
    assert "Defaults:root !use_pty" in body


def test_generate_sudoers_includes_container_paths(tmp_path: Path) -> None:
    config = {
        "terminal": {
            "host_execution": {
                "enabled": True,
                "service_user": "root",
                "allowed_commands": ["termgr", "grep", "casmgr"],
                "run_as": {
                    "default": "project_owner",
                    "sudo": {
                        "casmgr": {
                            "as_user": "casuser",
                            "path": "/usr/bin/casmgr",
                        }
                    },
                    "command_paths": {
                        "termgr": "/usr/local/bin/termgr",
                        "grep": "/usr/bin/grep",
                    },
                },
            }
        }
    }
    cfg_path = tmp_path / "term_server.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")
    body = generate_sudoers_body(cfg_path)
    assert "root ALL=(ALL) NOPASSWD:" in body
    assert "/usr/local/bin/termgr" in body
    assert "/usr/bin/grep" in body
    assert "root ALL=(casuser) NOPASSWD: /usr/bin/casmgr" in body
    assert "/bin/bash" in body
    assert "Defaults:root !use_pty" in body
    assert "requiretty" not in body


def test_generated_sudoers_passes_visudo(tmp_path: Path) -> None:
    if shutil.which("visudo") is None:
        pytest.skip("visudo not installed")
    config = {
        "terminal": {
            "host_execution": {
                "enabled": True,
                "service_user": "root",
                "allowed_commands": ["bash"],
                "run_as": {"command_paths": {"bash": "/bin/bash"}},
            }
        }
    }
    cfg_path = tmp_path / "term_server.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")
    body = generate_sudoers_body(cfg_path)
    sudoers_tmp = tmp_path / "mcp-terminal"
    sudoers_tmp.write_text(body, encoding="utf-8")
    proc = subprocess.run(  # noqa: S603
        ["visudo", "-cf", str(sudoers_tmp)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_generate_sudoers_disabled(tmp_path: Path) -> None:
    cfg_path = tmp_path / "term_server.json"
    cfg_path.write_text(
        json.dumps({"terminal": {"host_execution": {"enabled": False}}}),
        encoding="utf-8",
    )
    body = generate_sudoers_body(cfg_path)
    assert "host_execution.enabled=false" in body
    assert "NOPASSWD" not in body


@pytest.mark.skipif(os.geteuid() != 0, reason="sync-host-sudo.sh requires root")
@pytest.mark.skipif(shutil.which("visudo") is None, reason="visudo not installed")
def test_sync_host_sudo_generates_valid_sudoers(tmp_path: Path) -> None:
    if not Path("/usr/bin/true").is_file():
        pytest.skip("/usr/bin/true not present")

    config = {
        "terminal": {
            "host_execution": {
                "enabled": True,
                "service_user": "root",
                "allowed_commands": ["true", "casmgr"],
                "run_as": {
                    "default": "project_owner",
                    "sudo": {
                        "casmgr": {
                            "as_user": "casuser",
                            "path": "/usr/bin/casmgr",
                        }
                    },
                    "command_paths": {
                        "true": "/usr/bin/true",
                    },
                },
            }
        }
    }
    cfg_path = tmp_path / "term_server.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")
    out_path = tmp_path / "mcp-terminal"
    proc = subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT), str(cfg_path)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "MCP_TERMINAL_SUDOERS_FILE": str(out_path)},
    )
    assert proc.returncode == 0, proc.stderr
    body = out_path.read_text(encoding="utf-8")
    assert "root ALL=(ALL) NOPASSWD:" in body
    assert "/usr/bin/true" in body
    assert "root ALL=(casuser) NOPASSWD: /usr/bin/casmgr" in body
    st = out_path.stat()
    assert oct(st.st_mode & 0o777) == "0o640"
    group_name = grp.getgrgid(st.st_gid).gr_name
    assert group_name == "mcp-terminal"
