"""terminal.host_execution config, chain validation, and routing."""

from __future__ import annotations

import logging

import pytest
from pathlib import Path

from mcp_terminal.config.config_generator import generate_terminal_config
from mcp_terminal.config.config_validator import validate_terminal_config
from mcp_terminal.config.host_execution_schema import HOST_EXECUTION_EMPTY_ALLOWLIST_LOG
from mcp_terminal.errors import ErrorCode
from mcp_terminal.services.host_execution_config import (
    HostExecutionConfig,
    HostSshConfig,
    decompose_shell_command,
    get_host_execution_config,
    is_host_execution_eligible,
    validate_host_run_request,
    validate_host_shell_command,
    validate_key_access_guard,
    warn_if_host_execution_enabled_without_commands,
)

_SSH = {
    "host": "127.0.0.1",
    "port": 22,
    "target_users": ["mcp-terminal-host"],
    "known_hosts_path": "/etc/mcp-terminal/ssh_known_hosts",
    "connect_timeout": 10,
    "key_manager_script": "/usr/lib/mcp-terminal/manage-session-keys.sh",
}

_CFG = {
    "terminal": {
        "host_execution": {
            "enabled": True,
            "allowed_commands": ["casmgr", "git", "pytest"],
            "ssh": _SSH,
        },
    }
}


def test_generator_includes_host_execution_defaults() -> None:
    cfg = generate_terminal_config({})
    he = cfg["terminal"]["host_execution"]
    assert he["enabled"] is False
    assert he["allowed_commands"] == []
    assert "ssh" in he
    assert validate_terminal_config(cfg) == []


def test_validator_requires_ssh_when_enabled() -> None:
    cfg = generate_terminal_config({})
    cfg["terminal"]["host_execution"]["enabled"] = True
    cfg["terminal"]["host_execution"]["allowed_commands"] = ["true"]
    cfg["terminal"]["host_execution"]["ssh"]["target_users"] = []
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "terminal.host_execution.ssh.target_users" in fields


def test_validator_rejects_obsolete_run_as() -> None:
    cfg = generate_terminal_config({})
    cfg["terminal"]["host_execution"]["run_as"] = {"default": "root"}
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "terminal.host_execution.run_as" in fields


def test_validator_accepts_enabled_with_ssh() -> None:
    cfg = generate_terminal_config(
        {},
        host_execution_enabled=True,
        host_execution_allowed_commands=["hostname"],
    )
    cfg["terminal"]["host_execution"]["ssh"] = dict(_SSH)
    assert validate_terminal_config(cfg) == []


def test_validator_rejects_bad_host_execution() -> None:
    cfg = generate_terminal_config({})
    cfg["terminal"]["host_execution"]["enabled"] = "yes"
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "terminal.host_execution.enabled" in fields


def test_forbidden_executables_override_empty_allows_docker() -> None:
    cfg = {
        "terminal": {
            "host_execution": {
                "enabled": True,
                "allowed_commands": ["docker"],
                "forbidden_executables_override": [],
                "ssh": _SSH,
            }
        }
    }
    he = get_host_execution_config(cfg)
    assert he.forbidden_executables == frozenset()
    v = validate_host_shell_command(
        "docker ps",
        he.allowed_commands,
        he.effective_forbidden_executables(),
    )
    assert v.ok


def test_decompose_shell_command_respects_quotes() -> None:
    parts = decompose_shell_command('casmgr status && git commit -m "a; b"')
    assert len(parts) == 2


def test_validate_chain_all_allowed() -> None:
    he = get_host_execution_config(_CFG)
    v = validate_host_shell_command("casmgr status && git status", he.allowed_commands)
    assert v.ok


def test_validate_host_run_disabled() -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "mcp_terminal.services.host_execution_config.get_host_execution_config",
            lambda: HostExecutionConfig(enabled=False, allowed_commands=frozenset({"casmgr"})),
        )
        v = validate_host_run_request("argv", None, ["casmgr"])
        assert not v.ok
        assert v.error_code == ErrorCode.HOST_EXECUTION_DISABLED


def test_key_guard_rejects_private_key_path(tmp_path: Path) -> None:
    session_dir = tmp_path / "s"
    session_dir.mkdir()
    key_dir = session_dir / ".ssh"
    key_dir.mkdir()
    private = key_dir / "session_ed25519"
    private.write_text("secret", encoding="utf-8")
    v = validate_key_access_guard(
        "shell",
        f"cat {private}",
        None,
        session_dir,
    )
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_KEY_ACCESS_FORBIDDEN


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


def test_parse_ssh_config() -> None:
    he = get_host_execution_config(_CFG)
    assert he.ssh is not None
    assert he.ssh.host == "127.0.0.1"
    assert he.ssh.default_target_user == "mcp-terminal-host"
    assert he.ssh_ready()
