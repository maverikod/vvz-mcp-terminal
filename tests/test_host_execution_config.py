"""terminal.host_execution config, chain validation, and routing."""

from __future__ import annotations

import logging

import pytest

from mcp_terminal.config.config_generator import generate_terminal_config
from mcp_terminal.config.config_validator import validate_terminal_config
from mcp_terminal.config.host_execution_schema import HOST_EXECUTION_EMPTY_ALLOWLIST_LOG
from mcp_terminal.errors import ErrorCode
from mcp_terminal.services.host_execution_config import (
    decompose_shell_command,
    get_host_execution_config,
    is_host_execution_eligible,
    validate_host_shell_command,
    warn_if_host_execution_enabled_without_commands,
)
from mcp_terminal.services.host_execution_config import validate_host_run_request

_CFG = {
    "terminal": {
        "host_execution": {"enabled": True, "allowed_commands": ["casmgr", "git", "pytest"]},
    }
}


def test_generator_includes_host_execution_defaults() -> None:
    cfg = generate_terminal_config({})
    he = cfg["terminal"]["host_execution"]
    assert he["enabled"] is False
    assert he["allowed_commands"] == []
    assert validate_terminal_config(cfg) == []


def test_validator_rejects_bad_host_execution() -> None:
    cfg = generate_terminal_config({})
    cfg["terminal"]["host_execution"]["enabled"] = "yes"
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "terminal.host_execution.enabled" in fields


def test_decompose_shell_command_respects_quotes() -> None:
    parts = decompose_shell_command('casmgr status && git commit -m "a; b"')
    assert len(parts) == 2
    assert parts[0] == "casmgr status"
    assert 'git commit -m "a; b"' in parts[1]


def test_validate_chain_all_allowed() -> None:
    he = get_host_execution_config(_CFG)
    v = validate_host_shell_command("casmgr status && git status", he.allowed_commands)
    assert v.ok
    assert len(v.segments) == 2


def test_validate_chain_rejects_disallowed_segment() -> None:
    he = get_host_execution_config(_CFG)
    v = validate_host_shell_command("casmgr status && docker ps", he.allowed_commands)
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_FORBIDDEN_COMMAND


def test_validate_forbidden_in_redirect_target() -> None:
    he = get_host_execution_config(_CFG)
    v = validate_host_shell_command(
        "pytest -q > /var/run/docker.sock",
        he.allowed_commands,
    )
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_FORBIDDEN_COMMAND
    assert "redirect" in (v.detail or "")


def test_validate_host_run_disabled() -> None:
    with pytest.MonkeyPatch.context() as mp:
        from mcp_terminal.services.host_execution_config import HostExecutionConfig

        mp.setattr(
            "mcp_terminal.services.host_execution_config.get_host_execution_config",
            lambda: HostExecutionConfig(enabled=False, allowed_commands=frozenset({"casmgr"})),
        )
        v = validate_host_run_request("argv", None, ["casmgr"])
        assert not v.ok
        assert v.error_code == ErrorCode.HOST_EXECUTION_DISABLED


def test_is_host_execution_eligible_requires_enabled() -> None:
    cfg = generate_terminal_config({})
    assert not is_host_execution_eligible("argv", None, ["true"], config=cfg)
    assert is_host_execution_eligible("argv", None, ["pytest", "-q"], config=_CFG)


def test_warn_when_enabled_and_empty_allowlist(caplog: pytest.LogCaptureFixture) -> None:
    cfg = generate_terminal_config({})
    cfg["terminal"]["host_execution"]["enabled"] = True
    with caplog.at_level(logging.WARNING):
        warn_if_host_execution_enabled_without_commands(cfg)
    assert HOST_EXECUTION_EMPTY_ALLOWLIST_LOG in caplog.text
