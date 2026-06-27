"""Root integration tests for ensure-host-permissions.sh."""

from __future__ import annotations

import grp
import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1] / "docker" / "pkg" / "ensure-host-permissions.sh"
)


def test_ensure_host_permissions_shell_syntax() -> None:
    proc = subprocess.run(  # noqa: S603
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_ensure_host_permissions_syncs_host_exec_keys_to_root() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "sync_host_exec_keys_to_root" in text
    assert "/root/.ssh/authorized_keys" in text
    assert "session_ed25519.pub" in text


def test_ensure_host_permissions_creates_stable_host_exec_key() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "ensure_stable_host_exec_key" in text
    assert "host_exec/.ssh" in text
    assert "ssh-keygen" in text


def _require_mcp_terminal_identity() -> None:
    if os.geteuid() != 0:
        pytest.skip("ensure-host-permissions.sh requires root")
    try:
        grp.getgrnam("mcp-terminal")
    except KeyError:
        pytest.skip("mcp-terminal group not present")


@pytest.mark.skipif(os.geteuid() != 0, reason="ensure-host-permissions.sh requires root")
def test_ensure_host_permissions_fixes_sudoers_and_mtls_modes(tmp_path: Path) -> None:
    _require_mcp_terminal_identity()

    sudoers = tmp_path / "mcp-terminal"
    sudoers.write_text("# test sudoers\n", encoding="utf-8")
    os.chown(sudoers, 0, 0)
    os.chmod(sudoers, 0o440)

    mtls = tmp_path / "mtls"
    key_dir = mtls / "server"
    key_dir.mkdir(parents=True)
    key_file = key_dir / "mcp-proxy.key"
    key_file.write_text("secret\n", encoding="utf-8")
    os.chown(key_file, 0, 0)
    os.chmod(key_file, 0o600)
    os.chown(mtls, 0, 0)
    os.chmod(mtls, 0o755)

    log_dir = tmp_path / "log"
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "term_server.json"
    config_file.write_text("{}", encoding="utf-8")

    env = {
        **os.environ,
        "MCP_TERMINAL_SUDOERS_FILE": str(sudoers),
        "MCP_TERMINAL_MTLS_DIR": str(mtls),
        "MCP_TERMINAL_LOG_DIR": str(log_dir),
        "MCP_TERMINAL_DATA_DIR": str(data_dir),
        "MCP_TERMINAL_CONFIG_DIR": str(config_dir),
        "MCP_TERMINAL_CONFIG_FILE": "term_server.json",
    }
    proc = subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout

    sudo_st = sudoers.stat()
    assert stat.S_IMODE(sudo_st.st_mode) == 0o640
    assert grp.getgrgid(sudo_st.st_gid).gr_name == "mcp-terminal"

    key_st = key_file.stat()
    assert stat.S_IMODE(key_st.st_mode) == 0o640
    assert grp.getgrgid(key_st.st_gid).gr_name == "mcp-terminal"

    mtls_st = mtls.stat()
    assert stat.S_IMODE(mtls_st.st_mode) == 0o750
