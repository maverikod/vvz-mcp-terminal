"""
Host-side command execution policy from ``terminal.host_execution``.

Shell chain parsing and forbidden-pattern scanning is delegated to
mcp_terminal/services/host_shell_scanner.py.

Use ``terminal_host_exec`` (not ``terminal_run``) for real host execution via SSH.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional

from mcp_terminal.config.host_execution_schema import (
    DEFAULT_SSH_KEY_MANAGER_SCRIPT,
    DEFAULT_SSH_KNOWN_HOSTS_PATH,
    HOST_EXECUTION_CONFIG,
    HOST_EXECUTION_EMPTY_ALLOWLIST_LOG,
    HOST_EXECUTION_SSH_INCOMPLETE_LOG,
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
    "HostSshConfig",
    "collect_shell_scan_texts",
    "command_executable_name",
    "decompose_shell_command",
    "find_forbidden_in_shell_command",
    "find_forbidden_substring",
    "get_host_execution_config",
    "host_shell_command_is_safe",
    "is_host_execution_eligible",
    "iter_shell_scan_fragments",
    "resolve_target_user",
    "segment_executable_name",
    "shell_command_has_chain",
    "validate_host_argv_command",
    "validate_host_run_request",
    "validate_host_shell_command",
    "validate_key_access_guard",
    "warn_if_host_execution_enabled_without_commands",
    "warn_if_host_ssh_incomplete",
]


@dataclass(frozen=True)
class HostSshConfig:
    """SSH connection settings for real host execution."""

    host: str
    port: int
    target_users: tuple[str, ...]
    known_hosts_path: str
    connect_timeout: int
    key_manager_script: str

    @property
    def default_target_user(self) -> str:
        return self.target_users[0]


@dataclass(frozen=True)
class HostExecutionConfig:
    """Resolved terminal.host_execution from server config."""

    enabled: bool
    allowed_commands: FrozenSet[str]
    forbidden_executables: Optional[FrozenSet[str]] = None
    ssh: Optional[HostSshConfig] = None
    """When set, replaces ``DEFAULT_HOST_FORBIDDEN_EXECUTABLES`` entirely (empty = none)."""

    def effective_forbidden_executables(self) -> FrozenSet[str]:
        if self.forbidden_executables is not None:
            return self.forbidden_executables
        return HOST_FORBIDDEN_EXECUTABLES

    def ssh_ready(self) -> bool:
        return (
            self.ssh is not None
            and bool(self.ssh.target_users)
            and bool(self.ssh.known_hosts_path.strip())
        )


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


def _parse_ssh(section: Dict[str, Any]) -> Optional[HostSshConfig]:
    raw = section.get("ssh")
    if not isinstance(raw, dict):
        defaults = HOST_EXECUTION_CONFIG.get("ssh")
        if not isinstance(defaults, dict):
            return None
        raw = defaults

    host = raw.get("host", HOST_EXECUTION_CONFIG["ssh"]["host"])
    if not isinstance(host, str) or not host.strip():
        host = str(HOST_EXECUTION_CONFIG["ssh"]["host"])

    port = raw.get("port", HOST_EXECUTION_CONFIG["ssh"]["port"])
    if not isinstance(port, int) or port < 1 or port > 65535:
        port = int(HOST_EXECUTION_CONFIG["ssh"]["port"])

    users: List[str] = []
    raw_users = raw.get("target_users", HOST_EXECUTION_CONFIG["ssh"]["target_users"])
    if isinstance(raw_users, list):
        for item in raw_users:
            if isinstance(item, str) and item.strip():
                users.append(item.strip())

    known_hosts = raw.get(
        "known_hosts_path",
        HOST_EXECUTION_CONFIG["ssh"]["known_hosts_path"],
    )
    if not isinstance(known_hosts, str) or not known_hosts.strip():
        known_hosts = DEFAULT_SSH_KNOWN_HOSTS_PATH

    connect_timeout = raw.get(
        "connect_timeout",
        HOST_EXECUTION_CONFIG["ssh"]["connect_timeout"],
    )
    if not isinstance(connect_timeout, int) or connect_timeout < 1:
        connect_timeout = int(HOST_EXECUTION_CONFIG["ssh"]["connect_timeout"])

    key_script = raw.get(
        "key_manager_script",
        HOST_EXECUTION_CONFIG["ssh"]["key_manager_script"],
    )
    if not isinstance(key_script, str) or not key_script.strip():
        key_script = DEFAULT_SSH_KEY_MANAGER_SCRIPT

    return HostSshConfig(
        host=host.strip(),
        port=port,
        target_users=tuple(users),
        known_hosts_path=known_hosts.strip(),
        connect_timeout=connect_timeout,
        key_manager_script=key_script.strip(),
    )


def _parse_forbidden_executables_override(section: Dict[str, Any]) -> Optional[FrozenSet[str]]:
    if "forbidden_executables_override" not in section:
        return None
    raw = section.get("forbidden_executables_override")
    if not isinstance(raw, list):
        return None
    return frozenset(
        item.strip().lower()
        for item in raw
        if isinstance(item, str) and item.strip()
    )


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

    forbidden_executables = _parse_forbidden_executables_override(section)
    ssh = _parse_ssh(section)

    return HostExecutionConfig(
        enabled=enabled,
        allowed_commands=frozenset(names),
        forbidden_executables=forbidden_executables,
        ssh=ssh,
    )


def resolve_target_user(
    requested: Optional[str],
    *,
    config: HostExecutionConfig | None = None,
) -> tuple[Optional[str], Optional[str]]:
    """Resolve target_user; return (user, error_code)."""
    he = config or get_host_execution_config()
    if he.ssh is None or not he.ssh.target_users:
        return None, ErrorCode.HOST_EXECUTION_DISABLED
    if requested is None or not str(requested).strip():
        return he.ssh.default_target_user, None
    user = str(requested).strip()
    if user not in he.ssh.target_users:
        return None, ErrorCode.TARGET_USER_NOT_ALLOWED
    return user, None


def warn_if_host_execution_enabled_without_commands(config: Dict[str, Any]) -> None:
    """Log a reminder when host execution is on but the allowlist is empty."""
    he = get_host_execution_config(config)
    if he.enabled and not he.allowed_commands:
        _logger.warning(HOST_EXECUTION_EMPTY_ALLOWLIST_LOG)


def warn_if_host_ssh_incomplete(config: Dict[str, Any]) -> None:
    """Log when host execution is enabled but SSH settings are incomplete."""
    he = get_host_execution_config(config)
    if he.enabled and he.allowed_commands and not he.ssh_ready():
        _logger.warning(HOST_EXECUTION_SSH_INCOMPLETE_LOG)


def _command_text_fragments(
    execution_kind: str,
    command: Optional[str],
    argv: Optional[List[str]],
) -> List[str]:
    """User-supplied command text only (not session key paths)."""
    fragments: List[str] = []
    if execution_kind == "shell" and command:
        fragments.append(command)
        for frag in iter_shell_scan_fragments(command):
            if isinstance(frag, tuple):
                fragments.append(str(frag[0]))
            else:
                fragments.append(str(frag))
    elif execution_kind == "argv" and argv:
        fragments.extend(str(x) for x in argv)
    return fragments


def validate_key_access_guard(
    execution_kind: str,
    command: Optional[str],
    argv: Optional[List[str]],
    session_dir: Path,
) -> HostCommandValidation:
    """Reject commands that reference the session private key path (R-KEY-GUARD)."""
    from mcp_terminal.services.session_ssh_key import (  # noqa: PLC0415
        SESSION_KEY_DIRNAME,
        SESSION_KEY_FILENAME,
        session_key_paths,
    )

    priv, pub = session_key_paths(session_dir)
    priv_resolved = str(priv.resolve())
    pub_resolved = str(pub.resolve())
    key_dir_resolved = str((session_dir / SESSION_KEY_DIRNAME).resolve())
    key_rel = f"{SESSION_KEY_DIRNAME}/{SESSION_KEY_FILENAME}"

    needles = [
        priv_resolved,
        pub_resolved,
        key_dir_resolved,
        key_rel,
        SESSION_KEY_FILENAME,
    ]

    for fragment in _command_text_fragments(execution_kind, command, argv):
        if not fragment:
            continue
        frag_lower = fragment.lower()
        for needle in needles:
            if not needle:
                continue
            if needle in fragment or needle.lower() in frag_lower:
                return HostCommandValidation(
                    ok=False,
                    error_code=ErrorCode.HOST_KEY_ACCESS_FORBIDDEN,
                    detail="command references session SSH key material",
                )
        if SESSION_KEY_DIRNAME in frag_lower and SESSION_KEY_FILENAME in frag_lower:
            return HostCommandValidation(
                ok=False,
                error_code=ErrorCode.HOST_KEY_ACCESS_FORBIDDEN,
                detail="command references session SSH key file",
            )
    return HostCommandValidation(ok=True)


def _allowed_names_lower(allowed: FrozenSet[str]) -> FrozenSet[str]:
    return {name.lower() for name in allowed}


def _validate_segment(
    segment: str,
    allowed_lower: FrozenSet[str],
    forbidden_executables: FrozenSet[str],
) -> HostCommandValidation:
    exe = segment_executable_name(segment)
    if not exe:
        return HostCommandValidation(
            ok=False,
            error_code=ErrorCode.HOST_COMMAND_NOT_ALLOWED,
            detail="could not determine executable for segment",
            segments=(segment,),
        )

    exe_lower = exe.lower()
    if exe_lower in forbidden_executables:
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
    forbidden_executables: Optional[FrozenSet[str]] = None,
) -> HostCommandValidation:
    """Validate every segment of a shell command for host execution."""
    blocked = (
        forbidden_executables
        if forbidden_executables is not None
        else HOST_FORBIDDEN_EXECUTABLES
    )
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
        result = _validate_segment(segment, allowed_lower, blocked)
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
    forbidden_executables: Optional[FrozenSet[str]] = None,
) -> HostCommandValidation:
    """Validate a single argv invocation for host execution."""
    blocked = (
        forbidden_executables
        if forbidden_executables is not None
        else HOST_FORBIDDEN_EXECUTABLES
    )
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
    if exe_lower in blocked:
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
    *,
    session_dir: Optional[Path] = None,
    target_user: Optional[str] = None,
) -> HostCommandValidation:
    """Require enabled host_execution and validate allowlist / forbidden / key-guard."""
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
    if not he.ssh_ready():
        return HostCommandValidation(
            ok=False,
            error_code=ErrorCode.HOST_EXECUTION_DISABLED,
            detail="terminal.host_execution.ssh is incomplete (target_users, known_hosts_path)",
        )

    _user, tu_err = resolve_target_user(target_user, config=he)
    if tu_err is not None:
        return HostCommandValidation(
            ok=False,
            error_code=tu_err,
            detail="target_user is not in terminal.host_execution.ssh.target_users",
        )

    if session_dir is not None:
        key_guard = validate_key_access_guard(execution_kind, command, argv, session_dir)
        if not key_guard.ok:
            return key_guard

    if execution_kind == "argv":
        if not argv:
            return HostCommandValidation(
                ok=False,
                error_code=ErrorCode.HOST_COMMAND_NOT_ALLOWED,
                detail="argv is required for execution_kind argv",
            )
        return validate_host_argv_command(
            [str(x) for x in argv],
            he.allowed_commands,
            he.effective_forbidden_executables(),
        )

    if execution_kind != "shell" or not command or not command.strip():
        return HostCommandValidation(
            ok=False,
            error_code=ErrorCode.HOST_COMMAND_NOT_ALLOWED,
            detail="command is required for execution_kind shell",
        )
    return validate_host_shell_command(
        command.strip(),
        he.allowed_commands,
        he.effective_forbidden_executables(),
    )


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
        if not he.enabled or not he.allowed_commands or not he.ssh_ready():
            return False
        if execution_kind == "argv" and argv:
            return validate_host_argv_command(
                [str(x) for x in argv],
                he.allowed_commands,
                he.effective_forbidden_executables(),
            ).ok
        if execution_kind == "shell" and command and command.strip():
            return validate_host_shell_command(
                command.strip(),
                he.allowed_commands,
                he.effective_forbidden_executables(),
            ).ok
        return False
    return validate_host_run_request(execution_kind, command, argv).ok


def host_shell_command_is_safe(command: str) -> bool:
    """Backward-compatible: True when shell text passes host chain validation."""
    he = get_host_execution_config()
    if not he.enabled or not he.allowed_commands:
        return False
    return validate_host_shell_command(
        command,
        he.allowed_commands,
        he.effective_forbidden_executables(),
    ).ok
