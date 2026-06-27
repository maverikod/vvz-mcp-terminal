"""Tests for config runtime preflight."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_terminal.config.config_runtime_checks import (
    assert_config_runtime_ready,
    collect_config_runtime_issues,
)


def _minimal_config(tmp_path: Path) -> dict:
    cert = tmp_path / "client.crt"
    key = tmp_path / "client.key"
    ca = tmp_path / "ca.crt"
    server_pem = tmp_path / "server.pem"
    for path in (cert, key, ca, server_pem):
        path.write_text("dummy", encoding="utf-8")
    watch = tmp_path / "watch"
    watch.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return {
        "server": {
            "protocol": "https",
            "log_dir": str(log_dir),
            "ssl": {"cert": str(server_pem), "key": str(server_pem), "ca": str(ca)},
        },
        "registration": {
            "enabled": True,
            "protocol": "https",
            "instance_uuid": str(uuid.uuid4()),
            "ssl": {"cert": str(cert), "key": str(key), "ca": str(ca)},
        },
        "code_analysis": {
            "enabled": True,
            "protocol": "https",
            "host": "127.0.0.1",
            "port": 15000,
            "timeout_seconds": 30,
            "ssl": {"cert": str(cert), "key": str(key), "ca": str(ca)},
        },
        "watch_dirs": {"directories": [str(watch)]},
    }


def test_runtime_ready_passes_with_valid_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MCP_TERMINAL_SKIP_DOCKER_PREFLIGHT", "1")
    monkeypatch.setenv("MCP_TERMINAL_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    cfg_path = tmp_path / "term_server.json"
    cfg_path.write_text("{}", encoding="utf-8")
    assert_config_runtime_ready(_minimal_config(tmp_path), config_path=cfg_path)


def test_runtime_ready_fails_on_missing_cert(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MCP_TERMINAL_SKIP_DOCKER_PREFLIGHT", "1")
    monkeypatch.setenv("MCP_TERMINAL_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    cfg_path = tmp_path / "term_server.json"
    cfg_path.write_text("{}", encoding="utf-8")
    config = _minimal_config(tmp_path)
    config["server"]["ssl"]["cert"] = str(tmp_path / "missing.pem")
    with pytest.raises(ValueError, match="not found"):
        assert_config_runtime_ready(config, config_path=cfg_path)


def test_runtime_ready_fails_on_replace_on_install_uuid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MCP_TERMINAL_SKIP_DOCKER_PREFLIGHT", "1")
    monkeypatch.setenv("MCP_TERMINAL_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    cfg_path = tmp_path / "term_server.json"
    cfg_path.write_text("{}", encoding="utf-8")
    config = _minimal_config(tmp_path)
    config["registration"]["instance_uuid"] = "REPLACE_ON_INSTALL"
    with pytest.raises(ValueError, match="REPLACE_ON_INSTALL"):
        assert_config_runtime_ready(config, config_path=cfg_path)


def test_runtime_ready_watch_dir_missing_hints_bind_mount(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MCP_TERMINAL_SKIP_DOCKER_PREFLIGHT", "1")
    monkeypatch.setenv("MCP_TERMINAL_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    cfg_path = tmp_path / "term_server.json"
    cfg_path.write_text("{}", encoding="utf-8")
    config = _minimal_config(tmp_path)
    config["watch_dirs"] = {"directories": ["/nonexistent/mcp-terminal-test-watch-root"]}
    monkeypatch.setenv("MCP_TERMINAL_CONFIG_DIR", "/etc/mcp-terminal")
    with pytest.raises(ValueError, match="not visible inside container"):
        assert_config_runtime_ready(config, config_path=cfg_path)


def test_runtime_warns_on_install_ca_for_code_analysis(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MCP_TERMINAL_SKIP_DOCKER_PREFLIGHT", "1")
    monkeypatch.setenv("MCP_TERMINAL_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    cfg_path = tmp_path / "term_server.json"
    cfg_path.write_text("{}", encoding="utf-8")
    config = _minimal_config(tmp_path)
    install_ca = tmp_path / "install-ca.crt"
    install_ca.write_text("dummy", encoding="utf-8")
    config["code_analysis"]["ssl"]["ca"] = str(install_ca)
    with patch(
        "mcp_terminal.config.config_runtime_checks._pem_subject",
        return_value="subject=CN = mcp-terminal-install-ca",
    ):
        issues = collect_config_runtime_issues(config, config_path=cfg_path)
    assert any("MCP-Proxy-Root-CA" in issue.message for issue in issues)


def test_runtime_warns_when_host_execution_secrets_path_missing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MCP_TERMINAL_SKIP_DOCKER_PREFLIGHT", "1")
    monkeypatch.setenv("MCP_TERMINAL_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    cfg_path = tmp_path / "term_server.json"
    cfg_path.write_text("{}", encoding="utf-8")
    config = _minimal_config(tmp_path)
    config["terminal"] = {
        "host_execution": {
            "enabled": True,
            "allowed_commands": ["true"],
            "secrets_path": str(tmp_path / "missing-secrets"),
            "ssh": {
                "host": "127.0.0.1",
                "port": 22,
                "target_users": ["mcp-terminal-host"],
                "known_hosts_path": str(tmp_path / "known_hosts"),
            },
        }
    }
    (tmp_path / "known_hosts").write_text("dummy", encoding="utf-8")
    issues = collect_config_runtime_issues(config, config_path=cfg_path)
    assert any(
        issue.field == "terminal.host_execution.secrets_path"
        and "host commands will be disabled" in issue.message
        for issue in issues
    )


@patch("mcp_terminal.config.config_runtime_checks.subprocess.run")
@patch("mcp_terminal.config.config_runtime_checks.os.access", return_value=True)
@patch("mcp_terminal.config.config_runtime_checks.shutil.which", return_value="/usr/bin/docker")
@patch("mcp_terminal.config.config_runtime_checks.Path.exists", return_value=True)
def test_check_docker_environment_rejects_old_api(
    _exists: MagicMock,
    _which: MagicMock,
    _access: MagicMock,
    mock_run: MagicMock,
) -> None:
    from mcp_terminal.config.config_runtime_checks import _check_docker_environment

    mock_run.return_value = MagicMock(returncode=0, stdout="1.41\n", stderr="")
    issues = _check_docker_environment()
    assert any(issue.level == "error" and "too old" in issue.message for issue in issues)
