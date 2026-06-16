"""Tests for config runtime preflight."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from mcp_terminal.config.config_runtime_checks import assert_config_runtime_ready


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


def test_runtime_ready_passes_with_valid_files(tmp_path: Path) -> None:
    cfg_path = tmp_path / "term_server.json"
    cfg_path.write_text("{}", encoding="utf-8")
    assert_config_runtime_ready(_minimal_config(tmp_path), config_path=cfg_path)


def test_runtime_ready_fails_on_missing_cert(tmp_path: Path) -> None:
    cfg_path = tmp_path / "term_server.json"
    cfg_path.write_text("{}", encoding="utf-8")
    config = _minimal_config(tmp_path)
    config["server"]["ssl"]["cert"] = str(tmp_path / "missing.pem")
    with pytest.raises(ValueError, match="not found"):
        assert_config_runtime_ready(config, config_path=cfg_path)


def test_runtime_ready_fails_on_replace_on_install_uuid(tmp_path: Path) -> None:
    cfg_path = tmp_path / "term_server.json"
    cfg_path.write_text("{}", encoding="utf-8")
    config = _minimal_config(tmp_path)
    config["registration"]["instance_uuid"] = "REPLACE_ON_INSTALL"
    with pytest.raises(ValueError, match="REPLACE_ON_INSTALL"):
        assert_config_runtime_ready(config, config_path=cfg_path)
