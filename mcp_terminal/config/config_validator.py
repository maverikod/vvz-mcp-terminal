"""
Config validator overlay for mcp_terminal (C-013).

Extends adapter SimpleConfigValidator with terminal-specific checks.
Must call adapter validation first, then terminal-specific layer.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class ValidationError:
    """Single terminal config validation error."""

    field: str  # dot-separated config path e.g. "terminal.sessions.ttl_seconds"
    message: str  # human-readable reason


def validate_terminal_config(
    config: Dict[str, Any],
) -> List[ValidationError]:
    """Validate terminal-specific config sections.

    Must be called AFTER adapter SimpleConfigValidator.validate().
    Checks all terminal-specific invariants.

    Args:
        config: Config dict that has already passed adapter validation.

    Returns:
        List of ValidationError; empty list means valid.
    """
    errors: List[ValidationError] = []
    terminal = config.get("terminal", {})
    sessions = terminal.get("sessions", {})
    # ttl_seconds required and positive
    ttl = sessions.get("ttl_seconds")
    if ttl is None:
        errors.append(
            ValidationError(
                field="terminal.sessions.ttl_seconds",
                message="terminal.sessions.ttl_seconds is required",
            )
        )
    elif not isinstance(ttl, (int, float)) or ttl <= 0:
        errors.append(
            ValidationError(
                field="terminal.sessions.ttl_seconds",
                message="terminal.sessions.ttl_seconds must be a positive number",
            )
        )
    # cleanup_interval positive
    interval = sessions.get("cleanup_interval_seconds")
    if interval is not None and (not isinstance(interval, (int, float)) or interval <= 0):
        errors.append(
            ValidationError(
                field="terminal.sessions.cleanup_interval_seconds",
                message="cleanup_interval_seconds must be positive",
            )
        )
    # max_sessions >= 1
    max_sessions = sessions.get("max_sessions_per_project")
    if max_sessions is not None and (not isinstance(max_sessions, int) or max_sessions < 1):
        errors.append(
            ValidationError(
                field="terminal.sessions.max_sessions_per_project",
                message="max_sessions_per_project must be >= 1",
            )
        )
    # max_commands >= 1
    max_cmds = sessions.get("max_commands_per_session")
    if max_cmds is not None and (not isinstance(max_cmds, int) or max_cmds < 1):
        errors.append(
            ValidationError(
                field="terminal.sessions.max_commands_per_session",
                message="max_commands_per_session must be >= 1",
            )
        )
    # output limits positive
    output = terminal.get("output", {})
    for key in (
        "max_stdout_file_bytes",
        "max_stderr_file_bytes",
        "default_read_bytes",
        "max_read_bytes",
    ):
        val = output.get(key)
        if val is not None and (not isinstance(val, int) or val <= 0):
            errors.append(
                ValidationError(
                    field=f"terminal.output.{key}",
                    message=f"{key} must be a positive integer",
                )
            )
    # history limit consistency
    commands = terminal.get("commands", {})
    default_limit = commands.get("default_history_limit")
    max_limit = commands.get("max_history_limit")
    if default_limit is not None and max_limit is not None:
        if default_limit > max_limit:
            errors.append(
                ValidationError(
                    field="terminal.commands.default_history_limit",
                    message="default_history_limit must not exceed max_history_limit",
                )
            )

    errors.extend(_validate_terminal_defaults(terminal.get("defaults")))
    errors.extend(_validate_host_execution(terminal.get("host_execution")))
    errors.extend(_validate_runtime(config.get("runtime")))
    errors.extend(_validate_code_analysis(config.get("code_analysis")))
    errors.extend(_validate_watch_dirs(config.get("watch_dirs")))
    return errors


def _validate_terminal_defaults(section: Any) -> List[ValidationError]:
    """Validate ``terminal.defaults`` session/run defaults."""
    errors: List[ValidationError] = []
    if section is None:
        return errors
    if not isinstance(section, dict):
        errors.append(
            ValidationError(
                field="terminal.defaults",
                message="terminal.defaults must be an object when present",
            )
        )
        return errors
    ws = section.get("workspace_write")
    if ws is not None and not isinstance(ws, bool):
        errors.append(
            ValidationError(
                field="terminal.defaults.workspace_write",
                message="workspace_write must be a boolean",
            )
        )
    pid_ns = section.get("pid_namespace")
    if pid_ns is not None and str(pid_ns).lower() not in ("container", "host"):
        errors.append(
            ValidationError(
                field="terminal.defaults.pid_namespace",
                message="pid_namespace must be 'container' or 'host'",
            )
        )
    kc = section.get("keep_container")
    if kc is not None and not isinstance(kc, bool):
        errors.append(
            ValidationError(
                field="terminal.defaults.keep_container",
                message="keep_container must be a boolean",
            )
        )
    uv = section.get("use_venv")
    if uv is not None and not isinstance(uv, bool):
        errors.append(
            ValidationError(
                field="terminal.defaults.use_venv",
                message="use_venv must be a boolean",
            )
        )
    return errors


def _validate_host_execution(section: Any) -> List[ValidationError]:
    """Validate ``terminal.host_execution`` (optional host-side command allowlist)."""
    errors: List[ValidationError] = []
    if section is None:
        return errors
    if not isinstance(section, dict):
        errors.append(
            ValidationError(
                field="terminal.host_execution",
                message="terminal.host_execution must be an object when present",
            )
        )
        return errors

    enabled = section.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        errors.append(
            ValidationError(
                field="terminal.host_execution.enabled",
                message="enabled must be a boolean",
            )
        )

    commands = section.get("allowed_commands")
    if commands is None:
        return errors
    if not isinstance(commands, list):
        errors.append(
            ValidationError(
                field="terminal.host_execution.allowed_commands",
                message="allowed_commands must be an array of strings when present",
            )
        )
        return errors

    for i, item in enumerate(commands):
        if not isinstance(item, str) or not item.strip():
            errors.append(
                ValidationError(
                    field=f"terminal.host_execution.allowed_commands[{i}]",
                    message="each allowed_commands entry must be a non-empty string",
                )
            )
    return errors


def _validate_runtime(section: Any) -> List[ValidationError]:
    """Validate ``runtime`` sandbox defaults."""
    errors: List[ValidationError] = []
    if section is None:
        return errors
    if not isinstance(section, dict):
        errors.append(
            ValidationError(field="runtime", message="runtime must be an object when present")
        )
        return errors
    return errors


def _validate_code_analysis(section: Any) -> List[ValidationError]:
    """Validate optional top-level ``code_analysis`` (Code Analysis Server client)."""
    errors: List[ValidationError] = []
    if section is None:
        return errors
    if not isinstance(section, dict):
        errors.append(
            ValidationError(
                field="code_analysis",
                message="code_analysis must be an object when present",
            )
        )
        return errors

    enabled = section.get("enabled", False)
    if not isinstance(enabled, bool):
        errors.append(
            ValidationError(
                field="code_analysis.enabled",
                message="code_analysis.enabled must be a boolean",
            )
        )
        enabled = False

    proto = section.get("protocol", "https")
    if proto is not None and str(proto).lower() not in ("http", "https"):
        errors.append(
            ValidationError(
                field="code_analysis.protocol",
                message="code_analysis.protocol must be 'http' or 'https'",
            )
        )

    host = section.get("host")
    if enabled:
        if not isinstance(host, str) or not host.strip():
            errors.append(
                ValidationError(
                    field="code_analysis.host",
                    message=(
                        "code_analysis.host is required and must be a non-empty string when enabled"
                    ),
                )
            )

    port = section.get("port")
    if port is not None and (
        not isinstance(port, int) or isinstance(port, bool) or port < 1 or port > 65535
    ):
        errors.append(
            ValidationError(
                field="code_analysis.port",
                message="code_analysis.port must be an integer in 1..65535",
            )
        )
    if enabled and port is None:
        errors.append(
            ValidationError(
                field="code_analysis.port",
                message="code_analysis.port is required when enabled",
            )
        )

    path = section.get("jsonrpc_path", "/api/jsonrpc")
    if path is not None:
        if not isinstance(path, str) or not path.strip().startswith("/"):
            errors.append(
                ValidationError(
                    field="code_analysis.jsonrpc_path",
                    message=(
                        "code_analysis.jsonrpc_path must be a non-empty string starting with '/'"
                    ),
                )
            )

    timeout = section.get("timeout_seconds")
    if timeout is not None and (
        not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or float(timeout) <= 0
    ):
        errors.append(
            ValidationError(
                field="code_analysis.timeout_seconds",
                message="code_analysis.timeout_seconds must be a positive number",
            )
        )
    if enabled and timeout is None:
        errors.append(
            ValidationError(
                field="code_analysis.timeout_seconds",
                message="code_analysis.timeout_seconds is required when enabled",
            )
        )

    widx = section.get("watch_dir_index", 0)
    if widx is not None and (not isinstance(widx, int) or isinstance(widx, bool) or widx < 0):
        errors.append(
            ValidationError(
                field="code_analysis.watch_dir_index",
                message="code_analysis.watch_dir_index must be a non-negative integer",
            )
        )

    proto_s = str(proto).lower() if proto is not None else "https"
    ssl_block = section.get("ssl")
    if enabled and proto_s == "https":
        if not isinstance(ssl_block, dict):
            errors.append(
                ValidationError(
                    field="code_analysis.ssl",
                    message=(
                        "code_analysis.ssl object is required when enabled and protocol is https"
                    ),
                )
            )
        else:
            for key in ("cert", "key", "ca"):
                val = ssl_block.get(key)
                if not isinstance(val, str) or not val.strip():
                    errors.append(
                        ValidationError(
                            field=f"code_analysis.ssl.{key}",
                            message=(
                                f"code_analysis.ssl.{key} must be a non-empty string when enabled"
                            ),
                        )
                    )
            crl = ssl_block.get("crl")
            if crl is not None and crl != "" and not isinstance(crl, str):
                errors.append(
                    ValidationError(
                        field="code_analysis.ssl.crl",
                        message="code_analysis.ssl.crl must be a string or null",
                    )
                )
            for bool_key in ("dnscheck", "check_hostname"):
                if (
                    bool_key in ssl_block
                    and ssl_block[bool_key] is not None
                    and not isinstance(ssl_block[bool_key], bool)
                ):
                    errors.append(
                        ValidationError(
                            field=f"code_analysis.ssl.{bool_key}",
                            message=f"code_analysis.ssl.{bool_key} must be a boolean",
                        )
                    )
    elif (
        enabled
        and proto_s == "http"
        and ssl_block
        not in (
            None,
            {},
        )
    ):
        if isinstance(ssl_block, dict) and any(
            ssl_block.get(k) for k in ("cert", "key", "ca") if ssl_block.get(k)
        ):
            errors.append(
                ValidationError(
                    field="code_analysis.ssl",
                    message="code_analysis.ssl must be empty or omitted when protocol is http",
                )
            )

    return errors


def _validate_watch_dirs(section: Any) -> List[ValidationError]:
    """Validate optional ``watch_dirs`` (dirs that contain project roots + refresh)."""
    errors: List[ValidationError] = []
    if section is None:
        return errors
    if not isinstance(section, dict):
        errors.append(
            ValidationError(
                field="watch_dirs",
                message="watch_dirs must be an object when present",
            )
        )
        return errors

    directories = section.get("directories")
    if directories is not None:
        if not isinstance(directories, list):
            errors.append(
                ValidationError(
                    field="watch_dirs.directories",
                    message="watch_dirs.directories must be an array of strings when present",
                )
            )
        else:
            for i, item in enumerate(directories):
                if not isinstance(item, str):
                    errors.append(
                        ValidationError(
                            field=f"watch_dirs.directories[{i}]",
                            message="each watch_dirs.directories entry must be a string path",
                        )
                    )

    interval = section.get("refresh_interval_seconds")
    if interval is not None and (
        not isinstance(interval, (int, float)) or isinstance(interval, bool) or float(interval) < 0
    ):
        errors.append(
            ValidationError(
                field="watch_dirs.refresh_interval_seconds",
                message=(
                    "watch_dirs.refresh_interval_seconds must be a non-negative number "
                    "(0 disables background refresh)"
                ),
            )
        )

    return errors
