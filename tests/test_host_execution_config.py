"""terminal.host_execution config, chain validation, and routing."""

from __future__ import annotations

import logging

import pytest
from pathlib import Path

from mcp_terminal.config.config_generator import generate_terminal_config
from mcp_terminal.config.config_validator import validate_terminal_config
from mcp_terminal.config.host_execution_schema import (
    DEFAULT_HOST_EXECUTION_SECRETS_PATH,
    HOST_EXECUTION_EMPTY_ALLOWLIST_LOG,
)
from mcp_terminal.errors import ErrorCode
from mcp_terminal.services.host_execution_config import (
    HostExecutionConfig,
    HostSshConfig,
    decompose_shell_command,
    get_host_execution_config,
    host_secrets_path_issue,
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
    assert he["full_access"] is False
    assert he["allowed_commands"] == []
    assert he["secrets_path"] == DEFAULT_HOST_EXECUTION_SECRETS_PATH
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


def test_generator_accepts_host_execution_full_access() -> None:
    cfg = generate_terminal_config(
        {},
        host_execution_enabled=True,
        host_execution_full_access=True,
    )
    cfg["terminal"]["host_execution"]["ssh"] = dict(_SSH)
    he = cfg["terminal"]["host_execution"]
    assert he["full_access"] is True
    assert he["allowed_commands"] == []
    assert validate_terminal_config(cfg) == []


def test_generator_accepts_host_execution_secrets_path() -> None:
    cfg = generate_terminal_config(
        {},
        host_execution_secrets_path="/custom/host-exec-secrets",
    )
    assert (
        cfg["terminal"]["host_execution"]["secrets_path"]
        == "/custom/host-exec-secrets"
    )


def test_validator_rejects_bad_host_execution() -> None:
    cfg = generate_terminal_config({})
    cfg["terminal"]["host_execution"]["enabled"] = "yes"
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "terminal.host_execution.enabled" in fields


def test_validator_rejects_non_boolean_full_access() -> None:
    cfg = generate_terminal_config({})
    cfg["terminal"]["host_execution"]["full_access"] = "yes"
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "terminal.host_execution.full_access" in fields


def test_validator_rejects_non_string_secrets_path() -> None:
    cfg = generate_terminal_config({})
    cfg["terminal"]["host_execution"]["secrets_path"] = 123
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "terminal.host_execution.secrets_path" in fields


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


def test_validate_host_run_full_access_allows_any_command(tmp_path: Path) -> None:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir(mode=0o700)
    cfg = HostExecutionConfig(
        enabled=True,
        full_access=True,
        allowed_commands=frozenset(),
        secrets_path=str(secrets_dir),
        ssh=HostSshConfig(
            host="127.0.0.1",
            port=22,
            target_users=("mcp-terminal-host",),
            known_hosts_path="/etc/mcp-terminal/ssh_known_hosts",
            connect_timeout=10,
            key_manager_script="/usr/lib/mcp-terminal/manage-session-keys.sh",
        ),
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "mcp_terminal.services.host_execution_config.get_host_execution_config",
            lambda: cfg,
        )
        shell = validate_host_run_request("shell", "sudo docker ps && rm -rf /tmp/x", None)
        argv = validate_host_run_request("argv", None, ["kubectl", "get", "pods"])
    assert shell.ok
    assert argv.ok


def test_full_access_direct_validators_bypass_allowlist_and_denylist() -> None:
    shell = validate_host_shell_command(
        "sudo docker ps",
        frozenset(),
        frozenset({"sudo", "docker"}),
        full_access=True,
    )
    assert shell.ok


def test_full_access_ignores_configured_forbidden_override() -> None:
    cfg = {
        "terminal": {
            "host_execution": {
                "enabled": True,
                "full_access": True,
                "allowed_commands": [],
                "forbidden_executables_override": ["sudo", "docker"],
                "ssh": _SSH,
            }
        }
    }
    he = get_host_execution_config(cfg)
    assert he.forbidden_executables == frozenset({"sudo", "docker"})
    assert he.effective_forbidden_executables() == frozenset()


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


def test_session_key_paths_use_configured_secrets_path(tmp_path: Path) -> None:
    from mcp_terminal.services.session_ssh_key import session_key_paths

    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir(mode=0o700)
    session_dir = tmp_path / ".terminals" / "00000000-0000-4000-8000-000000000002"
    session_dir.mkdir(parents=True)
    cfg = HostExecutionConfig(
        enabled=True,
        allowed_commands=frozenset({"true"}),
        secrets_path=str(secrets_dir),
        ssh=HostSshConfig(
            host="127.0.0.1",
            port=22,
            target_users=("mcp-terminal-host",),
            known_hosts_path="/etc/mcp-terminal/ssh_known_hosts",
            connect_timeout=10,
            key_manager_script="/usr/lib/mcp-terminal/manage-session-keys.sh",
        ),
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "mcp_terminal.services.session_ssh_key.get_host_execution_config",
            lambda: cfg,
        )
        private, public = session_key_paths(session_dir)
    assert private == secrets_dir / session_dir.name / ".ssh" / "session_ed25519"
    assert public == secrets_dir / session_dir.name / ".ssh" / "session_ed25519.pub"


def test_is_host_execution_eligible_requires_enabled(tmp_path: Path) -> None:
    cfg = generate_terminal_config({})
    assert not is_host_execution_eligible("argv", None, ["true"], config=cfg)
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir(mode=0o700)
    enabled_cfg = {
        "terminal": {
            "host_execution": {
                **_CFG["terminal"]["host_execution"],
                "secrets_path": str(secrets_dir),
            }
        }
    }
    assert is_host_execution_eligible("argv", None, ["pytest", "-q"], config=enabled_cfg)


def test_is_host_execution_eligible_allows_full_access(tmp_path: Path) -> None:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir(mode=0o700)
    cfg = {
        "terminal": {
            "host_execution": {
                "enabled": True,
                "full_access": True,
                "allowed_commands": [],
                "secrets_path": str(secrets_dir),
                "ssh": _SSH,
            }
        }
    }
    assert is_host_execution_eligible("argv", None, ["not-in-allowlist"], config=cfg)


def test_host_secrets_path_issue_rejects_empty() -> None:
    assert host_secrets_path_issue("") == "terminal.host_execution.secrets_path is empty"


def test_host_secrets_path_issue_rejects_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    assert "not found" in (host_secrets_path_issue(str(missing)) or "")


def test_host_secrets_path_issue_rejects_broad_permissions(tmp_path: Path) -> None:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir(mode=0o755)
    assert "permissions are too broad" in (host_secrets_path_issue(str(secrets_dir)) or "")


def test_validate_host_run_rejects_invalid_secrets_path(tmp_path: Path) -> None:
    cfg = HostExecutionConfig(
        enabled=True,
        allowed_commands=frozenset({"casmgr"}),
        secrets_path=str(tmp_path / "missing"),
        ssh=HostSshConfig(
            host="127.0.0.1",
            port=22,
            target_users=("mcp-terminal-host",),
            known_hosts_path="/etc/mcp-terminal/ssh_known_hosts",
            connect_timeout=10,
            key_manager_script="/usr/lib/mcp-terminal/manage-session-keys.sh",
        ),
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "mcp_terminal.services.host_execution_config.get_host_execution_config",
            lambda: cfg,
        )
        v = validate_host_run_request("argv", None, ["casmgr"])
    assert not v.ok
    assert v.error_code == ErrorCode.HOST_EXECUTION_DISABLED
    assert v.detail is not None
    assert "secrets_path" in v.detail


def test_warn_when_enabled_and_empty_allowlist(caplog: pytest.LogCaptureFixture) -> None:
    cfg = generate_terminal_config({})
    cfg["terminal"]["host_execution"]["enabled"] = True
    with caplog.at_level(logging.WARNING):
        warn_if_host_execution_enabled_without_commands(cfg)
    assert HOST_EXECUTION_EMPTY_ALLOWLIST_LOG in caplog.text


def test_no_empty_allowlist_warning_when_full_access(caplog: pytest.LogCaptureFixture) -> None:
    cfg = generate_terminal_config({})
    cfg["terminal"]["host_execution"]["enabled"] = True
    cfg["terminal"]["host_execution"]["full_access"] = True
    with caplog.at_level(logging.WARNING):
        warn_if_host_execution_enabled_without_commands(cfg)
    assert HOST_EXECUTION_EMPTY_ALLOWLIST_LOG not in caplog.text


def test_parse_ssh_config() -> None:
    he = get_host_execution_config(_CFG)
    assert he.ssh is not None
    assert he.ssh.host == "127.0.0.1"
    assert he.ssh.default_target_user == "mcp-terminal-host"
    assert he.ssh_ready()
