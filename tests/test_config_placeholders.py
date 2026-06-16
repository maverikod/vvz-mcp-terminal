"""Tests for install-time config placeholder detection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_terminal.config.config_placeholders import (
    UNRESOLVED_PLACEHOLDER_MARKERS,
    assert_config_placeholders_resolved,
    config_text_has_unresolved_placeholders,
    list_unresolved_placeholder_hints,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO_ROOT / "docker" / "packaging" / "term_server.json.template"
TEST_TERM_PATH = REPO_ROOT / "configs" / "_test_term.json"


def test_packaging_template_exists() -> None:
    assert TEMPLATE_PATH.is_file()


def test_packaging_template_full_terminal_shape() -> None:
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    data = json.loads(text)
    assert data["server"]["advertised_host"] == "CHANGE_ME"
    assert "MCP_PROXY_HOST" in data["registration"]["register_url"]
    assert data["registration"]["instance_uuid"] == "REPLACE_ON_INSTALL"
    assert "terminal" in data
    assert "host_execution" in data["terminal"]
    assert data["terminal"]["host_execution"]["enabled"] is True
    assert "runtime" in data
    assert data["code_analysis"]["enabled"] is True
    assert data["code_analysis"]["host"] == "CODE_ANALYSIS_HOST"
    assert data["code_analysis"]["port"] == 15010
    assert data["watch_dirs"]["directories"] == ["WATCH_DIRS_ROOT"]


def test_test_term_minimal_adapter_placeholders() -> None:
    text = TEST_TERM_PATH.read_text(encoding="utf-8")
    data = json.loads(text)
    assert data["server"]["advertised_host"] == "CHANGE_ME"
    assert "MCP_PROXY_HOST" in data["registration"]["register_url"]
    assert data["registration"]["instance_uuid"] == "REPLACE_ON_INSTALL"
    assert "terminal" not in data
    assert "runtime" not in data
    assert "code_analysis" not in data


def test_config_text_has_unresolved_placeholders() -> None:
    assert config_text_has_unresolved_placeholders(TEMPLATE_PATH.read_text(encoding="utf-8"))
    resolved = json.dumps(
        {
            "server": {"advertised_host": "10.0.0.1"},
            "registration": {
                "register_url": "https://proxy:3004/register",
                "instance_uuid": "00000000-0000-4000-8000-000000000001",
            },
            "code_analysis": {"enabled": True, "host": "127.0.0.1", "port": 15010},
            "watch_dirs": {"directories": ["/var/projects"]},
        }
    )
    assert not config_text_has_unresolved_placeholders(resolved)


def test_code_analysis_host_placeholder_always_flagged() -> None:
    text = json.dumps(
        {
            "code_analysis": {"enabled": False, "host": "CODE_ANALYSIS_HOST", "port": 15010},
        }
    )
    assert config_text_has_unresolved_placeholders(text)


def test_list_unresolved_placeholder_hints() -> None:
    hints = list_unresolved_placeholder_hints(TEMPLATE_PATH.read_text(encoding="utf-8"))
    assert "server.advertised_host (CHANGE_ME)" in hints
    assert "registration URLs (MCP_PROXY_HOST)" in hints
    assert any("code_analysis.host" in hint for hint in hints)
    assert any("WATCH_DIRS_ROOT" in hint for hint in hints)


def test_all_markers_documented() -> None:
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    for marker in UNRESOLVED_PLACEHOLDER_MARKERS:
        if marker in ("CODE_ANALYSIS_HOST", "WATCH_DIRS_ROOT"):
            assert marker in template_text
        elif marker == "REPLACE_ON_INSTALL":
            assert marker in template_text


def test_assert_config_placeholders_resolved_raises() -> None:
    with pytest.raises(ValueError, match="CHANGE_ME"):
        assert_config_placeholders_resolved(
            config_path="/etc/mcp-terminal/term_server.json",
            text=TEMPLATE_PATH.read_text(encoding="utf-8"),
        )
