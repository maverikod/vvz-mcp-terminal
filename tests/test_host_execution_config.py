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
    assert he["forbidden_executables_override"] is None
    assert validate_terminal_config(cfg) == []


def test_validator_accepts_run_as_root_without_allowed_commands() -> None:
    cfg = {
        "terminal": {
            "sessions": {"ttl_seconds": 3600},
            "host_execution": {
                "enabled": True,
                "forbidden_executables_override": [],
                "run_as": {"default": "root"},
            },
        }
    }
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "terminal.host_execution.run_as.default" not in fields
    assert "terminal.host_execution.forbidden_executables_override" not in fields


def test_generator_rejects_invalid_run_as_default_kwarg() -> None:
    import pytest

    with pytest.raises(ValueError, match="host_execution_run_as_default"):
        generate_terminal_config({}, host_execution_run_as_default="nobody")


def test_validator_rejects_bad_host_execution() -> None:
    cfg = generate_terminal_config({})
    cfg["terminal"]["host_execution"]["enabled"] = "yes"
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "terminal.host_execution.enabled" in fields


def test_validator_rejects_invalid_run_as_default() -> None:
    cfg = generate_terminal_config({})
    cfg["terminal"]["host_execution"]["run_as"]["default"] = "nobody"
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "terminal.host_execution.run_as.default" in fields


def test_validator_accepts_run_as_root() -> None:
    cfg = generate_terminal_config(
        {},
        host_execution_enabled=True,
        host_execution_allowed_commands=["docker"],
        host_execution_run_as_default="root",
    )
    assert validate_terminal_config(cfg) == []
    assert cfg["terminal"]["host_execution"]["run_as"]["default"] == "root"


def test_generator_cli_host_execution_overrides() -> None:
    from mcp_terminal.config.create_config import build_term_server_config

    cfg = build_term_server_config(
        host_execution_enabled=True,
        host_execution_allowed_commands=["docker", "systemctl"],
        host_execution_run_as_default="root",
        host_execution_service_user="root",
    )
    he = cfg["terminal"]["host_execution"]
    assert he["enabled"] is True
    assert he["allowed_commands"] == ["docker", "systemctl"]
    assert he["run_as"]["default"] == "root"
    assert he["service_user"] == "root"


def test_validator_rejects_bad_forbidden_executables_override() -> None:
    cfg = generate_terminal_config({})
    cfg["terminal"]["host_execution"]["forbidden_executables_override"] = "docker"
    fields = [e.field for e in validate_terminal_config(cfg)]
    assert "terminal.host_execution.forbidden_executables_override" in fields


def test_forbidden_executables_override_empty_allows_docker() -> None:
    cfg = {
        "terminal": {
            "host_execution": {
                "enabled": True,
                "allowed_commands": ["docker"],
                "forbidden_executables_override": [],
                "run_as": {"default": "root"},
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


def test_forbidden_executables_override_replaces_builtin_list() -> None:
    cfg = {
        "terminal": {
            "host_execution": {
                "enabled": True,
                "allowed_commands": ["docker", "kubectl"],
                "forbidden_executables_override": ["kubectl"],
            }
        }
    }
    he = get_host_execution_config(cfg)
    v_docker = validate_host_shell_command(
        "docker ps",
        he.allowed_commands,
        he.effective_forbidden_executables(),
    )
    assert v_docker.ok
    v_kubectl = validate_host_shell_command(
        "kubectl get pods",
        he.allowed_commands,
        he.effective_forbidden_executables(),
    )
    assert not v_kubectl.ok


def test_generator_cli_forbidden_executables_override() -> None:
    from mcp_terminal.config.create_config import build_term_server_config

    cfg = build_term_server_config(
        host_execution_enabled=True,
        host_execution_allowed_commands=["docker"],
        host_execution_forbidden_executables_override=[],
        host_execution_run_as_default="root",
    )
    he = cfg["terminal"]["host_execution"]
    assert he["forbidden_executables_override"] == []
    assert he["run_as"]["default"] == "root"


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


def test_parse_run_as_root_default() -> None:
    cfg = {
        "terminal": {
            "host_execution": {
                "enabled": True,
                "allowed_commands": ["docker"],
                "run_as": {"default": "root"},
            }
        }
    }
    he = get_host_execution_config(cfg)
    assert he.run_as_default == "root"


def test_parse_run_as_unknown_default_falls_back(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cfg = {
        "terminal": {
            "host_execution": {
                "enabled": True,
                "allowed_commands": ["docker"],
                "run_as": {"default": "nobody"},
            }
        }
    }
    with caplog.at_level(logging.WARNING):
        he = get_host_execution_config(cfg)
    assert he.run_as_default == "project_owner"
    assert "Unknown run_as.default" in caplog.text
