"""
Runtime filesystem checks for term server config (TLS material, paths, identity).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import stat
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence

from mcp_terminal.config.tls_protocol import effective_protocol, is_tls_protocol

IssueLevel = Literal["error", "warning"]

_SSL_PATH_KEYS = ("cert", "key", "ca", "crl")

# Docker Engine 29+ rejects API clients below 1.44 (embedded CLI in older images is 1.41).
_MIN_DOCKER_CLIENT_API = (1, 44)

_INSTALL_CA_MARKERS = ("mcp-terminal-install-ca", "MCP-Terminal/OU=CA")


@dataclass(frozen=True)
class RuntimeIssue:
    """One runtime preflight finding."""

    level: IssueLevel
    message: str
    field: Optional[str] = None


def _resolve_path(base: Path, raw: str) -> Path:
    candidate = Path(raw.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = (base / candidate).resolve()
    return candidate


def _section_active(section_name: str, section: dict, app_config: dict) -> bool:
    if section_name == "server":
        return True
    if section_name in ("client", "registration", "server_validation"):
        return bool(section.get("enabled", False))
    if section_name == "code_analysis":
        return bool(section.get("enabled", True))
    return True


def _collect_tls_file_checks(
    app_config: dict,
    *,
    config_path: Path,
) -> List[RuntimeIssue]:
    issues: List[RuntimeIssue] = []
    base = config_path.parent.resolve()

    for section_name in ("server", "client", "registration", "server_validation", "code_analysis"):
        section = app_config.get(section_name)
        if not isinstance(section, dict):
            if section_name == "code_analysis":
                issues.append(
                    RuntimeIssue("error", "code_analysis section is required", "code_analysis")
                )
            continue
        if not _section_active(section_name, section, app_config):
            continue
        proto = effective_protocol(section)
        if not is_tls_protocol(proto):
            continue
        ssl_block = section.get("ssl")
        if not isinstance(ssl_block, dict):
            issues.append(
                RuntimeIssue(
                    "error",
                    f"{section_name}.ssl object is required for protocol {proto}",
                    f"{section_name}.ssl",
                )
            )
            continue
        required_keys = ("cert", "key")
        if proto == "mtls" or section_name in ("server", "registration", "code_analysis"):
            required_keys = ("cert", "key", "ca")
        for key in required_keys:
            raw = ssl_block.get(key)
            if not isinstance(raw, str) or not raw.strip():
                issues.append(
                    RuntimeIssue(
                        "error",
                        f"{section_name}.ssl.{key} is required for protocol {proto}",
                        f"{section_name}.ssl.{key}",
                    )
                )
                continue
            path = _resolve_path(base, raw)
            if not path.is_file():
                issues.append(
                    RuntimeIssue(
                        "error",
                        f"{section_name}.ssl.{key} not found: {path}",
                        f"{section_name}.ssl.{key}",
                    )
                )
            elif not os.access(path, os.R_OK):
                issues.append(
                    RuntimeIssue(
                        "error",
                        f"{section_name}.ssl.{key} not readable: {path}",
                        f"{section_name}.ssl.{key}",
                    )
                )
        crl = ssl_block.get("crl")
        if crl is not None and crl != "":
            if not isinstance(crl, str) or not crl.strip():
                issues.append(
                    RuntimeIssue(
                        "error",
                        f"{section_name}.ssl.crl must be a non-empty string when set",
                        f"{section_name}.ssl.crl",
                    )
                )
            else:
                crl_path = _resolve_path(base, crl)
                if not crl_path.is_file():
                    issues.append(
                        RuntimeIssue(
                            "error",
                            f"{section_name}.ssl.crl not found: {crl_path}",
                            f"{section_name}.ssl.crl",
                        )
                    )
                elif not os.access(crl_path, os.R_OK):
                    issues.append(
                        RuntimeIssue(
                            "error",
                            f"{section_name}.ssl.crl not readable: {crl_path}",
                            f"{section_name}.ssl.crl",
                        )
                    )
    return issues


def _format_gid_hint(gid: int) -> str:
    try:
        import grp

        return f"group {grp.getgrgid(gid).gr_name} (gid {gid})"
    except (KeyError, OSError):
        return f"gid {gid}"


def _directory_traversable(path: Path) -> bool:
    """Return True when the current process can traverse/list *path*."""
    try:
        st = os.stat(path, follow_symlinks=True)
    except OSError:
        return False
    if not stat.S_ISDIR(st.st_mode):
        return False
    if os.access(path, os.R_OK | os.X_OK):
        return True
    mode = st.st_mode
    uid = os.getuid()
    groups = set(os.getgroups())
    if uid == st.st_uid and (mode & 0o500):
        return True
    if st.st_gid in groups and (mode & 0o050):
        return True
    return bool(mode & 0o005)


def _directory_writable(path: Path) -> bool:
    try:
        st = os.stat(path, follow_symlinks=True)
    except OSError:
        return False
    if not stat.S_ISDIR(st.st_mode):
        return False
    if os.access(path, os.W_OK):
        return True
    mode = st.st_mode
    uid = os.getuid()
    groups = set(os.getgroups())
    if uid == st.st_uid and (mode & 0o200):
        return True
    if st.st_gid in groups and (mode & 0o020):
        return True
    return bool(mode & 0o002)


def _watch_dir_entry_issue(index: int, raw: str) -> Optional[RuntimeIssue]:
    path = Path(raw.strip())
    try:
        if not path.exists():
            raise FileNotFoundError(path)
        if not path.is_dir():
            return RuntimeIssue(
                "error",
                f"watch_dirs.directories[{index}] exists but is not a directory: {path}",
                f"watch_dirs.directories[{index}]",
            )
    except FileNotFoundError:
        hint = ""
        if os.environ.get("MCP_TERMINAL_CONFIG_DIR"):
            hint = (
                f" — bind-mount into the service container "
                f"(set MCP_TERMINAL_EXTRA_BINDS={path}:{path} or recreate; "
                f"docker-run auto-binds watch_dirs when MCP_TERMINAL_AUTO_BIND_WATCH_DIRS=1)"
            )
        return RuntimeIssue(
            "error",
            f"watch_dirs.directories[{index}] not visible inside container{hint}: {path}",
            f"watch_dirs.directories[{index}]",
        )
    except PermissionError:
        return RuntimeIssue(
            "error",
            f"watch_dirs.directories[{index}] permission denied: {path} "
            f"(service user needs traverse/read; add mcp-terminal to the directory group "
            f"or relax mode, e.g. group rx on the path)",
            f"watch_dirs.directories[{index}]",
        )
    if not _directory_traversable(path):
        hint = "check bind-mount and group membership"
        try:
            st = os.stat(path, follow_symlinks=True)
            mode = st.st_mode & 0o777
            req = _format_gid_hint(st.st_gid)
            proc_groups = sorted(os.getgroups())
            extra = os.environ.get("MCP_TERMINAL_EXTRA_GROUPS", "").strip()
            hint = f"mode {oct(mode)} needs {req}; process gids={proc_groups}"
            if st.st_gid not in proc_groups:
                hint += (
                    f"; add {req} via MCP_TERMINAL_EXTRA_GROUPS in /etc/default/mcp-terminal "
                    f"and run: sudo mcp-terminal-docker recreate "
                    f"(docker-run also auto-adds --group-add from directory mode)"
                )
            if extra:
                hint += f"; configured MCP_TERMINAL_EXTRA_GROUPS={extra!r}"
        except OSError:
            pass
        return RuntimeIssue(
            "error",
            f"watch_dirs.directories[{index}] not traversable/readable: {path} ({hint})",
            f"watch_dirs.directories[{index}]",
        )
    if not _directory_writable(path):
        return RuntimeIssue(
            "warning",
            f"watch_dirs.directories[{index}] is not writable: {path} "
            f"(terminal_session_create needs create .terminals/ under project roots; "
            f"set group write on project dirs or run service with project-owner access)",
            f"watch_dirs.directories[{index}]",
        )
    return None


def _iter_project_roots(watch_root: Path, *, limit: int = 3) -> List[Path]:
    """Return up to *limit* immediate child dirs that look like registered projects."""
    found: List[Path] = []
    try:
        children = sorted(watch_root.iterdir())
    except OSError:
        return found
    for child in children:
        if not child.is_dir():
            continue
        if (child / "projectid").is_file():
            found.append(child)
            if len(found) >= limit:
                break
            continue
        try:
            for nested in sorted(child.iterdir()):
                if nested.is_dir() and (nested / "projectid").is_file():
                    found.append(nested)
                    if len(found) >= limit:
                        return found
        except OSError:
            continue
    return found


def _check_watch_dirs(app_config: dict) -> List[RuntimeIssue]:
    issues: List[RuntimeIssue] = []
    watch_dirs = app_config.get("watch_dirs")
    if not isinstance(watch_dirs, dict):
        return issues
    directories = watch_dirs.get("directories")
    if not isinstance(directories, list):
        return issues
    if not directories:
        issues.append(
            RuntimeIssue(
                "warning",
                "watch_dirs.directories is empty — project registry will stay empty",
                "watch_dirs.directories",
            )
        )
    for i, item in enumerate(directories):
        if not isinstance(item, str) or not item.strip():
            issues.append(
                RuntimeIssue(
                    "error",
                    f"watch_dirs.directories[{i}] must be a non-empty path",
                    f"watch_dirs.directories[{i}]",
                )
            )
            continue
        issue = _watch_dir_entry_issue(i, item)
        if issue:
            issues.append(issue)
            continue
        watch_path = Path(item.strip())
        for project_dir in _iter_project_roots(watch_path):
            if not _directory_writable(project_dir):
                issues.append(
                    RuntimeIssue(
                        "warning",
                        f"project dir not writable for .terminals: {project_dir} "
                        f"(owner uid/gid {project_dir.stat().st_uid}/{project_dir.stat().st_gid}; "
                        f"service uid {os.getuid()} groups {sorted(os.getgroups())}; "
                        f"chmod g+w on project or add MCP_TERMINAL_EXTRA_GROUPS)",
                        "watch_dirs.directories",
                    )
                )
                break
    return issues


def _check_log_dir(app_config: dict) -> List[RuntimeIssue]:
    issues: List[RuntimeIssue] = []
    server = app_config.get("server")
    if not isinstance(server, dict):
        return issues
    raw = server.get("log_dir")
    if not isinstance(raw, str) or not raw.strip():
        return issues
    path = Path(raw.strip())
    if path.is_dir():
        if not os.access(path, os.W_OK):
            issues.append(
                RuntimeIssue("error", f"server.log_dir not writable: {path}", "server.log_dir")
            )
        return issues
    parent = path.parent
    if not parent.is_dir() or not os.access(parent, os.W_OK):
        issues.append(
            RuntimeIssue(
                "error",
                f"server.log_dir cannot be created (parent not writable): {path}",
                "server.log_dir",
            )
        )
    return issues


def _default_data_dir() -> Path:
    raw = os.environ.get("MCP_TERMINAL_DATA_DIR", "/var/mcp-terminal").strip()
    return Path(raw)


def _check_data_dir() -> List[RuntimeIssue]:
    issues: List[RuntimeIssue] = []
    path = _default_data_dir()
    if path.is_dir():
        if not os.access(path, os.W_OK):
            issues.append(
                RuntimeIssue("error", f"data dir not writable: {path}", "MCP_TERMINAL_DATA_DIR")
            )
        return issues
    parent = path.parent
    if not parent.is_dir() or not os.access(parent, os.W_OK):
        issues.append(
            RuntimeIssue(
                "error",
                f"data dir cannot be created (parent not writable): {path}",
                "MCP_TERMINAL_DATA_DIR",
            )
        )
    return issues


def _parse_api_version(raw: str) -> Optional[tuple[int, int]]:
    match = re.match(r"^(\d+)\.(\d+)", raw.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _check_docker_environment() -> List[RuntimeIssue]:
    issues: List[RuntimeIssue] = []
    sock = Path("/var/run/docker.sock")
    if not sock.exists():
        issues.append(
            RuntimeIssue(
                "error",
                "/var/run/docker.sock not found (bind-mount host socket for terminal_run)",
                "docker.sock",
            )
        )
    elif not os.access(sock, os.R_OK | os.W_OK):
        issues.append(
            RuntimeIssue(
                "error",
                "/var/run/docker.sock not accessible (add service user to docker group)",
                "docker.sock",
            )
        )

    docker_bin = os.environ.get("MCP_TERMINAL_DOCKER_BIN", "docker")
    if shutil.which(docker_bin) is None:
        issues.append(
            RuntimeIssue(
                "error",
                f"docker CLI not found ({docker_bin}); mount host /usr/bin/docker into container "
                f"(MCP_TERMINAL_MOUNT_HOST_DOCKER=1 in /etc/default/mcp-terminal)",
                "docker.cli",
            )
        )
        return issues

    try:
        proc = subprocess.run(
            [docker_bin, "version", "--format", "{{.Client.APIVersion}}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        issues.append(
            RuntimeIssue("error", f"docker version failed: {exc}", "docker.cli")
        )
        return issues

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        issues.append(
            RuntimeIssue(
                "error",
                f"docker CLI cannot talk to daemon: {detail or proc.returncode}",
                "docker.cli",
            )
        )
        return issues

    parsed = _parse_api_version(proc.stdout)
    if parsed is None:
        issues.append(
            RuntimeIssue(
                "warning",
                f"could not parse docker client API version: {proc.stdout.strip()!r}",
                "docker.cli",
            )
        )
        return issues
    if parsed < _MIN_DOCKER_CLIENT_API:
        issues.append(
            RuntimeIssue(
                "error",
                f"docker client API {parsed[0]}.{parsed[1]} is too old "
                f"(minimum {_MIN_DOCKER_CLIENT_API[0]}.{_MIN_DOCKER_CLIENT_API[1]}); "
                f"mount host /usr/bin/docker (see MCP_TERMINAL_MOUNT_HOST_DOCKER)",
                "docker.cli",
            )
        )
    return issues


def _check_instance_uuid(app_config: dict) -> List[RuntimeIssue]:
    issues: List[RuntimeIssue] = []
    registration = app_config.get("registration")
    if not isinstance(registration, dict):
        issues.append(
            RuntimeIssue("error", "registration section is required", "registration")
        )
        return issues
    raw = registration.get("instance_uuid")
    if not isinstance(raw, str) or not raw.strip():
        issues.append(
            RuntimeIssue("error", "registration.instance_uuid is required", "registration.instance_uuid")
        )
        return issues
    if raw.strip() == "REPLACE_ON_INSTALL":
        issues.append(
            RuntimeIssue(
                "error",
                "registration.instance_uuid is still REPLACE_ON_INSTALL",
                "registration.instance_uuid",
            )
        )
        return issues
    try:
        parsed = uuid.UUID(raw.strip())
    except ValueError:
        issues.append(
            RuntimeIssue(
                "error",
                "registration.instance_uuid must be a valid UUID",
                "registration.instance_uuid",
            )
        )
        return issues
    if parsed.version != 4:
        issues.append(
            RuntimeIssue(
                "error",
                "registration.instance_uuid must be UUID4",
                "registration.instance_uuid",
            )
        )
    return issues


def _check_code_analysis_transport(app_config: dict) -> List[RuntimeIssue]:
    issues: List[RuntimeIssue] = []
    section = app_config.get("code_analysis")
    if not isinstance(section, dict):
        issues.append(
            RuntimeIssue(
                "error",
                "code_analysis section is required for casmgr session gate",
                "code_analysis",
            )
        )
        return issues
    if section.get("enabled") is False:
        issues.append(
            RuntimeIssue(
                "warning",
                "code_analysis.enabled is false — terminal_session_create cannot validate casmgr sessions",
                "code_analysis.enabled",
            )
        )
    for field in ("host", "port", "timeout_seconds"):
        if section.get(field) in (None, ""):
            issues.append(
                RuntimeIssue(
                    "error",
                    f"code_analysis.{field} is required",
                    f"code_analysis.{field}",
                )
            )
    return issues


def _pem_subject(path: Path) -> str:
    try:
        proc = subprocess.run(
            ["openssl", "x509", "-in", str(path), "-noout", "-subject"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _check_code_analysis_ca(app_config: dict, *, config_path: Path) -> List[RuntimeIssue]:
    issues: List[RuntimeIssue] = []
    section = app_config.get("code_analysis")
    if not isinstance(section, dict) or section.get("enabled") is False:
        return issues
    ssl_block = section.get("ssl")
    if not isinstance(ssl_block, dict):
        return issues
    raw_ca = ssl_block.get("ca")
    if not isinstance(raw_ca, str) or not raw_ca.strip():
        return issues
    ca_path = _resolve_path(config_path.parent.resolve(), raw_ca)
    if not ca_path.is_file():
        return issues
    subject = _pem_subject(ca_path)
    if not subject:
        return issues
    if any(marker in subject for marker in _INSTALL_CA_MARKERS):
        issues.append(
            RuntimeIssue(
                "warning",
                f"code_analysis.ssl.ca looks like install-time CA ({ca_path}); "
                f"casmgr-server uses MCP-Proxy-Root-CA — copy "
                f"/etc/ai-editor/mtls_certificates/mtls_certificates/ca/ca.crt to "
                f"code_analysis.ssl.ca (see man mcp-terminal-config)",
                "code_analysis.ssl.ca",
            )
        )
    return issues


def _host_execution_enabled(app_config: dict) -> bool:
    terminal = app_config.get("terminal")
    if not isinstance(terminal, dict):
        return False
    host_exec = terminal.get("host_execution")
    if not isinstance(host_exec, dict):
        return False
    return bool(host_exec.get("enabled", False))


def _check_host_execution_ssh(app_config: dict) -> List[RuntimeIssue]:
    if not _host_execution_enabled(app_config):
        return []
    terminal = app_config.get("terminal")
    if not isinstance(terminal, dict):
        return []
    host_exec = terminal.get("host_execution")
    if not isinstance(host_exec, dict):
        return []
    ssh = host_exec.get("ssh")
    if not isinstance(ssh, dict):
        return [
            RuntimeIssue(
                "warning",
                "terminal.host_execution.enabled but ssh section is missing",
                "terminal.host_execution.ssh",
            )
        ]
    issues: List[RuntimeIssue] = []
    known_hosts = ssh.get("known_hosts_path")
    if isinstance(known_hosts, str) and known_hosts.strip():
        kh_path = Path(known_hosts.strip())
        if not kh_path.is_file():
            issues.append(
                RuntimeIssue(
                    "warning",
                    f"terminal.host_execution.ssh.known_hosts_path not found: {kh_path}",
                    "terminal.host_execution.ssh.known_hosts_path",
                )
            )
    key_script = ssh.get("key_manager_script", "/usr/lib/mcp-terminal/manage-session-keys.sh")
    if isinstance(key_script, str) and key_script.strip():
        script_path = Path(key_script.strip())
        if not script_path.is_file():
            issues.append(
                RuntimeIssue(
                    "warning",
                    f"ssh key manager script not found: {script_path}",
                    "terminal.host_execution.ssh.key_manager_script",
                )
            )
        elif not os.access(script_path, os.X_OK):
            issues.append(
                RuntimeIssue(
                    "warning",
                    f"ssh key manager script is not executable: {script_path}",
                    "terminal.host_execution.ssh.key_manager_script",
                )
            )
    target_users = ssh.get("target_users")
    if not isinstance(target_users, list) or not target_users:
        issues.append(
            RuntimeIssue(
                "warning",
                "terminal.host_execution.enabled but ssh.target_users is empty",
                "terminal.host_execution.ssh.target_users",
            )
        )
    return issues


def collect_config_runtime_issues(
    app_config: Dict[str, Any],
    *,
    config_path: Path,
) -> List[RuntimeIssue]:
    """Return all runtime preflight findings (errors and warnings)."""
    issues: List[RuntimeIssue] = []
    issues.extend(_check_code_analysis_transport(app_config))
    issues.extend(_collect_tls_file_checks(app_config, config_path=config_path))
    issues.extend(_check_code_analysis_ca(app_config, config_path=config_path))
    issues.extend(_check_watch_dirs(app_config))
    issues.extend(_check_log_dir(app_config))
    issues.extend(_check_data_dir())
    if os.environ.get("MCP_TERMINAL_SKIP_DOCKER_PREFLIGHT", "").strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        issues.extend(_check_docker_environment())
    issues.extend(_check_host_execution_ssh(app_config))
    issues.extend(_check_instance_uuid(app_config))
    return issues


def log_config_runtime_issues(
    logger: logging.Logger,
    issues: Sequence[RuntimeIssue],
    *,
    config_path: Path,
) -> None:
    """Write preflight findings to *logger* (ERROR for errors, WARNING for warnings)."""
    if not issues:
        logger.info("Config runtime preflight passed (%s)", config_path)
        return
    logger.error("Config runtime preflight (%s): %d finding(s)", config_path, len(issues))
    for issue in issues:
        prefix = f"[{issue.field}] " if issue.field else ""
        line = f"  - {prefix}{issue.message}"
        if issue.level == "error":
            logger.error(line)
        else:
            logger.warning(line)


def assert_config_runtime_ready(
    app_config: Dict[str, Any],
    *,
    config_path: Path,
) -> None:
    """Raise ``ValueError`` with aggregated error-level issues when preflight fails."""
    issues = collect_config_runtime_issues(app_config, config_path=config_path)
    errors = [issue for issue in issues if issue.level == "error"]
    if errors:
        lines = "\n  - ".join(issue.message for issue in errors)
        raise ValueError(f"Config runtime preflight failed ({config_path}):\n  - {lines}")
