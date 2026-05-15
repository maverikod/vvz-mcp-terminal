"""
Unit tests for domain invariants of mcp_terminal (C-016, C-013).

Covers config validation, marker validation, session seq allocation,
output reader stream rejection, and sandbox policy zero-trust checks.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

import pytest  # noqa: F401

from mcp_terminal.config.config_validator import validate_terminal_config
from mcp_terminal.services.command_history import CommandHistory
from mcp_terminal.services.output_reader import OutputReader
from mcp_terminal.services.project_registry import validate_marker_file
from mcp_terminal.services.sandbox_policy import SandboxPolicy


def test_config_validator_rejects_missing_ttl() -> None:
    """Config validator must reject missing ttl_seconds (C-013)."""
    errors = validate_terminal_config({})
    fields = [e.field for e in errors]
    assert "terminal.sessions.ttl_seconds" in fields


def test_config_validator_rejects_zero_ttl() -> None:
    errors = validate_terminal_config({"terminal": {"sessions": {"ttl_seconds": 0}}})
    fields = [e.field for e in errors]
    assert "terminal.sessions.ttl_seconds" in fields


def test_config_validator_rejects_default_limit_exceeds_max() -> None:
    config = {
        "terminal": {
            "sessions": {"ttl_seconds": 3600},
            "commands": {"default_history_limit": 300, "max_history_limit": 200},
        }
    }
    errors = validate_terminal_config(config)
    fields = [e.field for e in errors]
    assert "terminal.commands.default_history_limit" in fields


def test_marker_validation_rejects_non_json() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "projectid"
        marker.write_text("not json", encoding="utf-8")
        result, err = validate_marker_file(marker)
        assert result is None
        assert err is not None
        assert err.code == "invalid_json"


def test_marker_validation_rejects_missing_id() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "projectid"
        marker.write_text(json.dumps({"description": "test"}), encoding="utf-8")
        result, err = validate_marker_file(marker)
        assert result is None
        assert err is not None
        assert err.code == "missing_id"


def test_seq_to_prefix_zero_pads_to_6_digits() -> None:
    assert CommandHistory.seq_to_prefix(1) == "000001"
    assert CommandHistory.seq_to_prefix(999999) == "999999"
    assert CommandHistory.seq_to_prefix(25) == "000025"


def test_output_reader_rejects_invalid_stream() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        reader = OutputReader(Path(tmp))
        data, err = reader.read(1, "combined")
        assert data is None
        assert err == "INVALID_STREAM"


def test_sandbox_policy_rejects_missing_execution_kind() -> None:
    result = SandboxPolicy().validate(
        project_id="abc",
        execution_kind=None,
        cwd=None,
        mode="read_only",
        network="none",
        image_profile="python_dev_3_12",
        command=None,
        argv=None,
    )
    assert not result.permitted
    assert result.error_code == "INVALID_COMMAND"


def test_merged_project_anchor_dirs_empty_without_sources() -> None:
    """No watch_dirs paths and disabled CA yields no anchors (no repo_root fallback)."""
    from mcp_terminal.paths import repo_root
    from mcp_terminal.services.project_roots import (
        merged_project_anchor_dirs,
        resolve_projects_root_dir,
    )

    cfg_path = repo_root() / "configs" / "term_server.json"
    assert merged_project_anchor_dirs({}, config_path=cfg_path) == []
    assert merged_project_anchor_dirs(
        {"code_analysis": {"enabled": False}}, config_path=cfg_path
    ) == []
    assert merged_project_anchor_dirs(
        {"watch_dirs": {"directories": []}}, config_path=cfg_path
    ) == []
    for cfg in ({}, {"code_analysis": {"enabled": False}}):
        try:
            resolve_projects_root_dir(cfg, config_path=cfg_path)
        except ValueError as exc:
            assert "No project watch anchors" in str(exc)
        else:
            raise AssertionError("expected ValueError")


def _minimal_terminal() -> dict:
    return {"terminal": {"sessions": {"ttl_seconds": 3600}}}


def test_code_analysis_validator_rejects_bad_port() -> None:
    cfg = {
        **_minimal_terminal(),
        "code_analysis": {"enabled": False, "port": "not-int"},
    }
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "code_analysis.port" in fields


def test_code_analysis_validator_https_enabled_requires_ssl_material() -> None:
    cfg = {
        **_minimal_terminal(),
        "code_analysis": {
            "enabled": True,
            "protocol": "https",
            "host": "127.0.0.1",
            "port": 15000,
            "timeout_seconds": 30,
            "ssl": {"cert": "", "key": "", "ca": ""},
        },
    }
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "code_analysis.ssl.cert" in fields


def test_code_analysis_validator_http_rejects_nonempty_ssl_paths() -> None:
    cfg = {
        **_minimal_terminal(),
        "code_analysis": {
            "enabled": True,
            "protocol": "http",
            "host": "127.0.0.1",
            "port": 15000,
            "timeout_seconds": 30,
            "ssl": {"cert": "x.crt", "key": "", "ca": ""},
        },
    }
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "code_analysis.ssl" in fields


def test_generator_http_protocol_clears_ssl_and_validates() -> None:
    from mcp_terminal.config.config_generator import generate_terminal_config

    cfg = generate_terminal_config(
        {},
        code_analysis_enabled=True,
        code_analysis_protocol="http",
    )
    assert cfg["code_analysis"]["protocol"] == "http"
    assert cfg["code_analysis"]["ssl"] is None
    assert validate_terminal_config(cfg) == []


def test_watch_dirs_validator_rejects_bad_directories_type() -> None:
    cfg = {**_minimal_terminal(), "watch_dirs": {"directories": "not-a-list"}}
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "watch_dirs.directories" in fields


def test_generate_terminal_config_watch_dirs_kwargs() -> None:
    from mcp_terminal.config.config_generator import generate_terminal_config

    cfg = generate_terminal_config({}, watch_dirs_directories=["/tmp"])
    assert cfg["watch_dirs"]["directories"] == ["/tmp"]
    assert validate_terminal_config(cfg) == []


def test_generate_terminal_config_raises_on_invalid_terminal_override() -> None:
    from mcp_terminal.config.config_generator import generate_terminal_config

    with pytest.raises(ValueError, match="validate_terminal_config"):
        generate_terminal_config(
            {},
            overrides={"terminal": {"sessions": {"ttl_seconds": 0}}},
        )


def test_sandbox_policy_rejects_host_path_project_id() -> None:
    result = SandboxPolicy().validate(
        project_id="/home/user/projects",
        execution_kind="argv",
        cwd=None,
        mode="read_only",
        network="none",
        image_profile="python_dev_3_12",
        command=None,
        argv=["pytest"],
    )
    assert not result.permitted
    assert result.error_code == "PROJECT_PATH_OUT_OF_SCOPE"
