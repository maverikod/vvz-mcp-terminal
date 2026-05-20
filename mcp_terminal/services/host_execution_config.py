"""
Host-side command execution policy from ``terminal.host_execution``.

Shell chain parsing and forbidden-pattern scanning is delegated to
mcp_terminal/services/host_shell_scanner.py.

Use ``terminal_run_host`` (not ``terminal_run``) for host execution.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional

from mcp_terminal.config.host_execution_schema import (
    HOST_EXECUTION_CONFIG,
    HOST_EXECUTION_EMPTY_ALLOWLIST_LOG,
)
from mcp_terminal.errors import ErrorCode
from mcp_terminal.services.host_shell_scanner import (
    HOST_FORBIDDEN_EXECUTABLES,
    HOST_FORBIDDEN_SUBSTRINGS,
    collect_shell_scan_texts,
    command_executable_name,
    decompose_shell_command,
    find_forbidden_in_shell_command,
    find_forbidden_substring,
    iter_shell_scan_fragments,
    segment_executable_name,
    shell_command_has_chain,
)

_logger = logging.getLogger(__name__)

__all__ = [
    "HOST_FORBIDDEN_EXECUTABLES",
    "HOST_FORBIDDEN_SUBSTRINGS",
    "HostCommandValidation",
    "HostExecutionConfig",
    "collect_shell_scan_texts",
    "command_executable_name",
    "decompose_shell_command",
    "find_forbidden_in_shell_command",
    "find_forbidden_substring",
    "get_host_execution_config",
    "host_shell_command_is_safe",
    "is_host_execution_eligible",
    "iter_shell_scan_fragments",
    "segment_executable_name",
    "shell_command_has_chain",
    "validate_host_argv_command",
    "validate_host_run_request",
    "validate_host_shell_command",
    "warn_if_host_execution_enabled_without_commands",
]


@dataclass(frozen=True)
class HostExecutionConfig:
    """Resolved terminal.host_execution from server config."""

    enabled: bool
    allowed_commands: FrozenSet[str]


@dataclass(frozen=True)
class HostCommandValidation:
    """Result of allowlist + forbidden checks for one command or chain."""

    ok: bool
    error_code: Optional[str] = None
    detail: Optional[str] = None
    segments: tuple[str, ...] = ()


def _host_execution_section(config: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    terminal = config.get("terminal")
    if not isinstance(terminal, dict):
        return {}
    raw = terminal.get("host_execution")
    if not isinstance(raw, dict):
        return {}
    return raw


def get_host_execution_config(config: Dict[str, Any] | None = None) -> HostExecutionConfig:
    """Return merged host_execution settings (config + built-in fallbacks)."""
    if config is None:
        try:
            from mcp_proxy_adapter.config import get_config

            data = getattr(get_config(), "config_data", None)
            config = data if isinstance(data, dict) else {}
        except Exception:
            config = {}

    section = _host_execution_section(config)

    enabled = section.get("enabled", HOST_EXECUTION_CONFIG["enabled"])
    if not isinstance(enabled, bool):
        enabled = bool(HOST_EXECUTION_CONFIG["enabled"])

    raw_list = section.get("allowed_commands", HOST_EXECUTION_CONFIG["allowed_commands"])
    names: List[str] = []
    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())

    return HostExecutionConfig(enabled=enabled, allowed_commands=frozenset(names))


def warn_if_host_execution_enabled_without_commands(config: Dict[str, Any]) -> None:
    """Log a reminder when host execution is on but the allowlist is empty."""
    he = get_host_execution_config(config)
    if he.enabled and not he.allowed_commands:
        _logger.warning(HOST_EXECUTION_EMPTY_ALLOWLIST_LOG)


def _allowed_names_lower(allowed: FrozenSet[str]) -> FrozenSet[str]:
    return {name.lower() for name in allowed}


def _validate_segment(segment: str, allowed_lower: FrozenSet[str]) -> HostCommandValidation:
    exe = segment_executable_name(segment)
    if not exe:
        return HostCommandValidation(
            ok=False,
            error_code=ErrorCode.HOST_COMMAND_NOT_ALLOWED,
            detail="could not determine executable for segment",
            segments=(segment,),
        )

    exe_lower = exe.lower()
    if exe_lower in HOST_FORBIDDEN_EXECUTABLES:
        return HostCommandValidation(
            ok=False,
            error_code=ErrorCode.HOST_FORBIDDEN_COMMAND,
            detail=f"executable {exe!r} is forbidden on host",
            segments=(segment,),
        )

    if exe_lower not in allowed_lower:
        return HostCommandValidation(
            ok=False,
            error_code=ErrorCode.HOST_COMMAND_NOT_ALLOWED,
            detail=f"executable {exe!r} is not in host allowlist",
            segments=(segment,),
        )

    return HostCommandValidation(ok=True, segments=(segment,))


def validate_host_shell_command(
    command: str,
    allowed_commands: FrozenSet[str],
) -> HostCommandValidation:
    """Validate every segment of a shell command for host execution."""
    allowed_lower = _allowed_names_lower(allowed_commands)
    hit = find_forbidden_in_shell_command(command)
    if hit is not None:
        forbidden, ctx = hit
        return HostCommandValidation(
            ok=False,
            error_code=ErrorCode.HOST_FORBIDDEN_COMMAND,
            detail=f"{ctx} contains forbidden pattern: {forbidden!r}",
        )

    segments = decompose_shell_command(command)
    if not segments:
        return HostCommandValidation(
            ok=False,
            error_code=ErrorCode.HOST_COMMAND_NOT_ALLOWED,
            detail="empty shell command",
        )

    for segment in segments:
        result = _validate_segment(segment, allowed_lower)
        if not result.ok:
            return HostCommandValidation(
                ok=False,
                error_code=result.error_code,
                detail=result.detail,
                segments=tuple(segments),
            )

    return HostCommandValidation(ok=True, segments=tuple(segments))


def validate_host_argv_command(
    argv: List[str],
    allowed_commands: FrozenSet[str],
) -> HostCommandValidation:
    """Validate a single argv invocation for host execution."""
    if not argv:
        return HostCommandValidation(
            ok=False,
            error_code=ErrorCode.HOST_COMMAND_NOT_ALLOWED,
            detail="empty argv",
        )

    joined = " ".join(str(x) for x in argv)
    forbidden = find_forbidden_substring(joined)
    if forbidden is not None:
        return HostCommandValidation(
            ok=False,
            error_code=ErrorCode.HOST_FORBIDDEN_COMMAND,
            detail=f"argv contains forbidden pattern: {forbidden!r}",
        )

    allowed_lower = _allowed_names_lower(allowed_commands)
    exe = Path(str(argv[0])).name
    exe_lower = exe.lower()
    if exe_lower in HOST_FORBIDDEN_EXECUTABLES:
        return HostCommandValidation(
            ok=False,
            error_code=ErrorCode.HOST_FORBIDDEN_COMMAND,
            detail=f"executable {exe!r} is forbidden on host",
        )
    if exe_lower not in allowed_lower:
        return HostCommandValidation(
            ok=False,
            error_code=ErrorCode.HOST_COMMAND_NOT_ALLOWED,
            detail=f"executable {exe!r} is not in host allowlist",
        )

    return HostCommandValidation(ok=True, segments=(joined,))


def validate_host_run_request(
    execution_kind: str,
    command: Optional[str],
    argv: Optional[List[str]],
) -> HostCommandValidation:
    """Require ``terminal.host_execution.enabled`` and validate allowlist / forbidden rules."""
    he = get_host_execution_config()
    if not he.enabled:
        return HostCommandValidation(
            ok=False,
            error_code=ErrorCode.HOST_EXECUTION_DISABLED,
            detail=(
                "terminal.host_execution.enabled is false; use terminal_run for container "
                "execution or enable host_execution in config"
            ),
        )
    if not he.allowed_commands:
        return HostCommandValidation(
            ok=False,
            error_code=ErrorCode.HOST_EXECUTION_DISABLED,
            detail="terminal.host_execution.allowed_commands is empty",
        )

    if execution_kind == "argv":
        if not argv:
            return HostCommandValidation(
                ok=False,
                error_code=ErrorCode.HOST_COMMAND_NOT_ALLOWED,
                detail="argv is required for execution_kind argv",
            )
        return validate_host_argv_command([str(x) for x in argv], he.allowed_commands)

    if execution_kind != "shell" or not command or not command.strip():
        return HostCommandValidation(
            ok=False,
            error_code=ErrorCode.HOST_COMMAND_NOT_ALLOWED,
            detail="command is required for execution_kind shell",
        )
    return validate_host_shell_command(command.strip(), he.allowed_commands)


def is_host_execution_eligible(
    execution_kind: str,
    command: Optional[str],
    argv: Optional[List[str]],
    *,
    config: Dict[str, Any] | None = None,
) -> bool:
    """True when host execution is enabled and the request passes host validation."""
    if config is not None:
        he = get_host_execution_config(config)
        if not he.enabled or not he.allowed_commands:
            return False
        if execution_kind == "argv" and argv:
            return validate_host_argv_command([str(x) for x in argv], he.allowed_commands).ok
        if execution_kind == "shell" and command and command.strip():
            return validate_host_shell_command(command.strip(), he.allowed_commands).ok
        return False
    return validate_host_run_request(execution_kind, command, argv).ok


def host_shell_command_is_safe(command: str) -> bool:
    """Backward-compatible: True when shell text passes host chain validation."""
    he = get_host_execution_config()
    if not he.enabled or not he.allowed_commands:
        return False
    return validate_host_shell_command(command, he.allowed_commands).ok
