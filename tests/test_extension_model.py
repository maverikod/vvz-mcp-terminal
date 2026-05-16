"""
Extension model and import smoke tests for mcp_terminal (C-016, C-013).
"""

from __future__ import annotations

import pytest  # noqa: F401


def test_skeleton_imports_preserved() -> None:
    """Existing skeleton modules must remain importable (C-016)."""
    import mcp_terminal.paths
    import mcp_terminal.term_config

    assert hasattr(mcp_terminal.paths, "repo_root")
    assert hasattr(mcp_terminal.term_config, "load_validated_term_simple_config")


def test_terminal_domain_modules_importable() -> None:
    """All terminal domain modules must be importable without error."""
    from mcp_terminal.services.sandbox_policy import SandboxPolicy
    from mcp_terminal.services.sandbox_policy import (  # noqa: F401
        TERMINAL_TRUST_BOUNDARY,
    )
    from mcp_terminal.services.project_registry import ProjectRegistry  # noqa: F401
    from mcp_terminal.services.session_store import SessionStore  # noqa: F401
    from mcp_terminal.services.command_history import CommandHistory  # noqa: F401
    from mcp_terminal.services.output_reader import OutputReader  # noqa: F401
    from mcp_terminal.services.ttl_cleanup import TtlCleanupService  # noqa: F401
    from mcp_terminal.services.audit_writer import AuditWriter  # noqa: F401
    from mcp_terminal.services.container_runner import ContainerRunner  # noqa: F401
    from mcp_terminal.jobs.terminal_execution_job import TerminalExecutionJob  # noqa: F401
    from mcp_terminal.errors import ErrorCode  # noqa: F401
    from mcp_terminal.errors import ALL_ERROR_CODES
    from mcp_terminal.services.project_roots import resolve_projects_root_dir  # noqa: F401
    from mcp_terminal.config.config_generator import generate_terminal_config  # noqa: F401
    from mcp_terminal.config.config_validator import validate_terminal_config  # noqa: F401

    assert SandboxPolicy is not None
    assert len(ALL_ERROR_CODES) == 20


def test_command_modules_importable() -> None:
    """All terminal command modules must be importable (C-014)."""
    from mcp_terminal.commands.terminal_delete_command import TerminalDeleteCommand
    from mcp_terminal.commands.terminal_get_command import TerminalGetCommand  # noqa: F401
    from mcp_terminal.commands.terminal_get_status_command import (
        TerminalGetStatusCommand,
    )
    from mcp_terminal.commands.terminal_kill_command import TerminalKillCommand
    from mcp_terminal.commands.terminal_list_command import TerminalListCommand
    from mcp_terminal.commands.terminal_list_watch_command import (  # noqa: F401
        TerminalListWatchCommand,
    )
    from mcp_terminal.commands.terminal_read_command import TerminalReadCommand
    from mcp_terminal.commands.terminal_run_command import TerminalRunCommand
    from mcp_terminal.commands.terminal_search_commands_command import (  # noqa: F401
        TerminalSearchCommandsCommand,
    )
    from mcp_terminal.commands.terminal_search_output_command import (
        TerminalSearchOutputCommand,
    )
    from mcp_terminal.commands.terminal_get_session_bootstrap_command import (
        TerminalGetSessionBootstrapCommand,
    )
    from mcp_terminal.commands.terminal_session_create_command import (
        TerminalSessionCreateCommand,
    )
    from mcp_terminal.jobs.session_bootstrap_job import SessionBootstrapJob  # noqa: F401
    from mcp_terminal.commands.terminal_sessions_command import (  # noqa: F401
        TerminalSessionsCommand,
    )
    from mcp_terminal.commands.terminal_stat_command import TerminalStatCommand
    from mcp_terminal.commands.terminal_tail_command import TerminalTailCommand

    assert TerminalGetStatusCommand.name == "terminal_get_status"
    assert TerminalRunCommand.name == "terminal_run"
    assert TerminalSessionCreateCommand.name == "terminal_session_create"
    assert TerminalGetSessionBootstrapCommand.name == "terminal_get_session_bootstrap"
    assert TerminalReadCommand.name == "terminal_read"
    assert TerminalTailCommand.name == "terminal_tail"
    assert TerminalStatCommand.name == "terminal_stat"
    assert TerminalSearchOutputCommand.name == "terminal_search_output"
    assert TerminalDeleteCommand.name == "terminal_delete"
    assert TerminalKillCommand.name == "terminal_kill"
    assert TerminalListCommand.name == "terminal_list"
    assert TerminalListWatchCommand.name == "terminal_list_watch"


def test_config_overlay_generates_defaults() -> None:
    """ConfigOverlay generator produces valid terminal config defaults (C-013)."""
    from mcp_terminal.config.config_generator import generate_terminal_config
    from mcp_terminal.config.config_validator import validate_terminal_config

    config = generate_terminal_config({})
    assert "terminal" in config
    assert "watch_dirs" in config
    assert "code_analysis" in config
    assert config["terminal"]["sessions"]["ttl_seconds"] == 86400
    assert config["code_analysis"]["enabled"] is False
    errors = validate_terminal_config(config)
    assert errors == [], f"Unexpected validation errors: {errors}"


def test_error_codes_stable() -> None:
    """All 15 ErrorContract codes must be defined (C-015)."""
    from mcp_terminal.errors import ALL_ERROR_CODES

    assert "PROJECT_NOT_FOUND" in ALL_ERROR_CODES
    assert "INVALID_SESSION" in ALL_ERROR_CODES
    assert "CONTAINER_CLEANUP_FAILED" in ALL_ERROR_CODES
    assert len(ALL_ERROR_CODES) == 20
