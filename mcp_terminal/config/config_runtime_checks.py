"""
Runtime filesystem checks for term server config (TLS material, paths, identity).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_terminal.config.tls_protocol import effective_protocol, is_tls_protocol

_SSL_PATH_KEYS = ("cert", "key", "ca", "crl")


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
        return True
    return True


def _collect_tls_file_checks(
    app_config: dict,
    *,
    config_path: Path,
) -> List[str]:
    missing: List[str] = []
    base = config_path.parent.resolve()

    for section_name in ("server", "client", "registration", "server_validation", "code_analysis"):
        section = app_config.get(section_name)
        if not isinstance(section, dict):
            if section_name == "code_analysis":
                missing.append("code_analysis section is required")
            continue
        if not _section_active(section_name, section, app_config):
            continue
        proto = effective_protocol(section)
        if not is_tls_protocol(proto):
            continue
        ssl_block = section.get("ssl")
        if not isinstance(ssl_block, dict):
            missing.append(f"{section_name}.ssl object is required for protocol {proto}")
            continue
        required_keys = ("cert", "key")
        if proto == "mtls" or section_name in ("server", "registration", "code_analysis"):
            required_keys = ("cert", "key", "ca")
        for key in required_keys:
            raw = ssl_block.get(key)
            if not isinstance(raw, str) or not raw.strip():
                missing.append(f"{section_name}.ssl.{key} is required for protocol {proto}")
                continue
            path = _resolve_path(base, raw)
            if not path.is_file():
                missing.append(f"{section_name}.ssl.{key} not found: {path}")
            elif not os.access(path, os.R_OK):
                missing.append(f"{section_name}.ssl.{key} not readable: {path}")
        crl = ssl_block.get("crl")
        if crl is not None and crl != "":
            if not isinstance(crl, str) or not crl.strip():
                missing.append(f"{section_name}.ssl.crl must be a non-empty string when set")
            else:
                crl_path = _resolve_path(base, crl)
                if not crl_path.is_file():
                    missing.append(f"{section_name}.ssl.crl not found: {crl_path}")
                elif not os.access(crl_path, os.R_OK):
                    missing.append(f"{section_name}.ssl.crl not readable: {crl_path}")
    return missing


def _check_watch_dirs(app_config: dict) -> List[str]:
    issues: List[str] = []
    watch_dirs = app_config.get("watch_dirs")
    if not isinstance(watch_dirs, dict):
        return issues
    directories = watch_dirs.get("directories")
    if not isinstance(directories, list):
        return issues
    for i, item in enumerate(directories):
        if not isinstance(item, str) or not item.strip():
            issues.append(f"watch_dirs.directories[{i}] must be a non-empty path")
            continue
        path = Path(item.strip())
        if not path.is_dir():
            issues.append(f"watch_dirs.directories[{i}] not a directory: {path}")
        elif not os.access(path, os.R_OK | os.X_OK):
            issues.append(f"watch_dirs.directories[{i}] not traversable/readable: {path}")
    return issues


def _check_log_dir(app_config: dict) -> List[str]:
    issues: List[str] = []
    server = app_config.get("server")
    if not isinstance(server, dict):
        return issues
    raw = server.get("log_dir")
    if not isinstance(raw, str) or not raw.strip():
        return issues
    path = Path(raw.strip())
    if path.is_dir():
        if not os.access(path, os.W_OK):
            issues.append(f"server.log_dir not writable: {path}")
        return issues
    parent = path.parent
    if not parent.is_dir() or not os.access(parent, os.W_OK):
        issues.append(f"server.log_dir cannot be created (parent not writable): {path}")
    return issues


def _check_instance_uuid(app_config: dict) -> List[str]:
    issues: List[str] = []
    registration = app_config.get("registration")
    if not isinstance(registration, dict):
        issues.append("registration section is required")
        return issues
    raw = registration.get("instance_uuid")
    if not isinstance(raw, str) or not raw.strip():
        issues.append("registration.instance_uuid is required")
        return issues
    if raw.strip() == "REPLACE_ON_INSTALL":
        issues.append("registration.instance_uuid is still REPLACE_ON_INSTALL")
        return issues
    try:
        parsed = uuid.UUID(raw.strip())
    except ValueError:
        issues.append("registration.instance_uuid must be a valid UUID")
        return issues
    if parsed.version != 4:
        issues.append("registration.instance_uuid must be UUID4")
    return issues


def _check_code_analysis_transport(app_config: dict) -> List[str]:
    issues: List[str] = []
    section = app_config.get("code_analysis")
    if not isinstance(section, dict):
        issues.append("code_analysis section is required for casmgr session gate")
        return issues
    for field in ("host", "port", "timeout_seconds"):
        if section.get(field) in (None, ""):
            issues.append(f"code_analysis.{field} is required")
    return issues


def assert_config_runtime_ready(
    app_config: Dict[str, Any],
    *,
    config_path: Path,
) -> None:
    """Raise ``ValueError`` with aggregated issues when runtime preflight fails."""
    issues: List[str] = []
    issues.extend(_check_code_analysis_transport(app_config))
    issues.extend(_collect_tls_file_checks(app_config, config_path=config_path))
    issues.extend(_check_watch_dirs(app_config))
    issues.extend(_check_log_dir(app_config))
    issues.extend(_check_instance_uuid(app_config))
    if issues:
        lines = "\n  - ".join(issues)
        raise ValueError(f"Config runtime preflight failed ({config_path}):\n  - {lines}")
