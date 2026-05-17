"""
Config generator overlay for mcp_terminal (C-013).

Extends adapter SimpleConfigGenerator with terminal-specific sections.
Call the adapter generator first, then merge terminal defaults on top.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from mcp_terminal.config.config_validator import validate_terminal_config
from mcp_terminal.config.host_execution_schema import HOST_EXECUTION_CONFIG
from mcp_terminal.config.terminal_defaults_schema import TERMINAL_DEFAULTS_CONFIG

TERMINAL_CONFIG_DEFAULTS: Dict[str, Any] = {
    "terminal": {
        "defaults": copy.deepcopy(TERMINAL_DEFAULTS_CONFIG),
        "sessions": {
            "ttl_seconds": 86400,
            "cleanup_interval_seconds": 3600,
            "max_sessions_per_project": 50,
            "max_commands_per_session": 1000,
        },
        "output": {
            "max_stdout_file_bytes": 100_000_000,
            "max_stderr_file_bytes": 100_000_000,
            "default_read_bytes": 65536,
            "max_read_bytes": 262144,
        },
        "commands": {
            "default_history_limit": 25,
            "max_history_limit": 200,
            "default_tail_lines": 100,
            "max_tail_lines": 5000,
        },
        "cleanup": {
            "delete_expired_sessions": True,
            "delete_running_sessions": False,
        },
        "host_execution": copy.deepcopy(HOST_EXECUTION_CONFIG),
    },
    "runtime": {
        "default_image_profile": "python_dev_3_12",
        "default_network": "none",
        "timeout_seconds": 60,
        "max_timeout_seconds": 300,
        "memory": "1g",
        "cpus": 1.0,
        "pids_limit": 256,
        "max_concurrent_runs": 4,
        "cleanup_always": True,
    },
}

# Top-level section (alongside adapter sections in merged JSON): Code Analysis Server.
CODE_ANALYSIS_CONFIG_DEFAULTS: Dict[str, Any] = {
    "enabled": False,
    "protocol": "https",
    "host": "127.0.0.1",
    "port": 15000,
    "jsonrpc_path": "/api/jsonrpc",
    "timeout_seconds": 30,
    "watch_dir_index": 0,
    "ssl": {
        "cert": "../mtls_certificates/mtls_certificates/client/mcp-proxy.crt",
        "key": "../mtls_certificates/mtls_certificates/client/mcp-proxy.key",
        "ca": "../mtls_certificates/mtls_certificates/ca/ca.crt",
        "crl": None,
        "dnscheck": False,
        "check_hostname": False,
    },
}

# Top-level section: dirs that *contain* project roots as subdirs + registry refresh.
WATCH_DIRS_CONFIG_DEFAULTS: Dict[str, Any] = {
    "directories": [],
    "refresh_interval_seconds": 60,
}


def _deep_merge_dict(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Return copy of base with overlay merged recursively (dict values merged)."""
    out = copy.deepcopy(base)
    for key, val in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge_dict(out[key], val)
        else:
            out[key] = copy.deepcopy(val)
    return out


def generate_terminal_config(
    base_config: Dict[str, Any],
    *,
    overrides: Optional[Dict[str, Any]] = None,
    watch_dirs: Optional[Dict[str, Any]] = None,
    watch_dirs_directories: Optional[List[str]] = None,
    watch_dirs_refresh_interval_seconds: Optional[float] = None,
    code_analysis: Optional[Dict[str, Any]] = None,
    code_analysis_enabled: Optional[bool] = None,
    code_analysis_protocol: Optional[str] = None,
    code_analysis_host: Optional[str] = None,
    code_analysis_port: Optional[int] = None,
    code_analysis_jsonrpc_path: Optional[str] = None,
    code_analysis_timeout_seconds: Optional[float] = None,
    code_analysis_watch_dir_index: Optional[int] = None,
    code_analysis_ssl_cert: Optional[str] = None,
    code_analysis_ssl_key: Optional[str] = None,
    code_analysis_ssl_ca: Optional[str] = None,
    code_analysis_ssl_crl: Optional[str] = None,
    code_analysis_ssl_dnscheck: Optional[bool] = None,
    code_analysis_ssl_check_hostname: Optional[bool] = None,
    terminal_defaults_workspace_write: Optional[bool] = None,
    terminal_defaults_pid_namespace: Optional[str] = None,
    terminal_defaults_keep_container: Optional[bool] = None,
) -> Dict[str, Any]:
    """Merge terminal-specific default sections into base_config.

    The caller is responsible for invoking the adapter SimpleConfigGenerator
    first and passing the resulting dict as base_config. This function then
    deep-merges TERMINAL_CONFIG_DEFAULTS into it. Caller-supplied overrides
    are applied last.

    This implements the C-013 overlay pattern: adapter first, terminal layer
    second, caller overrides third.

    The ``code_analysis`` block configures TLS + JSON-RPC access to the Code
    Analysis Server for ``list_watch_dirs`` (same shape as ``registration``:
    host, protocol, ssl). Pass ``code_analysis=`` for a full partial dict, or
    use the ``code_analysis_*`` keyword arguments for individual fields.

    Args:
        base_config: Adapter-valid config dict already produced by calling
            adapter SimpleConfigGenerator. May be empty dict for testing.
        overrides: Optional terminal-specific overrides to apply on top of
            the merged defaults. Values at top level fully replace defaults.
        watch_dirs: Optional dict merged into the ``watch_dirs`` section after
            defaults (and after any existing section from ``base_config``).
        watch_dirs_directories: When set, replaces ``watch_dirs.directories`` entirely:
            each string is a host directory whose **direct subdirectories** are
            candidate project roots (must contain ``projectid``).
        watch_dirs_refresh_interval_seconds: Overrides ``watch_dirs.refresh_interval_seconds``.
        code_analysis: Optional dict merged into the ``code_analysis`` section
            after defaults (and after any existing section from ``base_config``).
        code_analysis_enabled: When set, overrides ``code_analysis.enabled``.
        code_analysis_protocol: Overrides ``code_analysis.protocol``.
        code_analysis_host: Overrides ``code_analysis.host``.
        code_analysis_port: Overrides ``code_analysis.port``.
        code_analysis_jsonrpc_path: Overrides ``code_analysis.jsonrpc_path``.
        code_analysis_timeout_seconds: Overrides ``code_analysis.timeout_seconds``.
        code_analysis_watch_dir_index: Overrides ``code_analysis.watch_dir_index``.
        code_analysis_ssl_cert: Overrides ``code_analysis.ssl.cert``.
        code_analysis_ssl_key: Overrides ``code_analysis.ssl.key``.
        code_analysis_ssl_ca: Overrides ``code_analysis.ssl.ca``.
        code_analysis_ssl_crl: Overrides ``code_analysis.ssl.crl``.
        code_analysis_ssl_dnscheck: Overrides ``code_analysis.ssl.dnscheck``.
        code_analysis_ssl_check_hostname: Overrides ``code_analysis.ssl.check_hostname``.
        terminal_defaults_workspace_write: Overrides ``terminal.defaults.workspace_write``.
        terminal_defaults_pid_namespace: Overrides ``terminal.defaults.pid_namespace``.
        terminal_defaults_keep_container: Overrides ``terminal.defaults.keep_container``.

    Returns:
        New dict containing adapter sections, ``terminal``, ``runtime``,
        ``watch_dirs``, and ``code_analysis`` when generated. The result is
        always checked with ``validate_terminal_config``; on failure a
        ``ValueError`` is raised.

    Raises:
        ValueError: When the merged config fails ``validate_terminal_config``.
        TypeError: When ``watch_dirs`` or ``code_analysis`` is not a dict when provided.
    """
    result = copy.deepcopy(base_config)
    for key, value in TERMINAL_CONFIG_DEFAULTS.items():
        if key not in result:
            result[key] = copy.deepcopy(value)
        elif isinstance(value, dict):
            for subkey, subval in value.items():
                result[key].setdefault(subkey, copy.deepcopy(subval))

    wd_section = copy.deepcopy(WATCH_DIRS_CONFIG_DEFAULTS)
    existing_watch_dirs = result.get("watch_dirs")
    if isinstance(existing_watch_dirs, dict):
        wd_section = _deep_merge_dict(wd_section, existing_watch_dirs)
    if watch_dirs is not None:
        if not isinstance(watch_dirs, dict):
            raise TypeError("watch_dirs must be a dict when provided")
        wd_section = _deep_merge_dict(wd_section, watch_dirs)
    if watch_dirs_directories is not None:
        if not isinstance(watch_dirs_directories, list):
            raise TypeError("watch_dirs_directories must be a list of strings when provided")
        wd_section["directories"] = list(watch_dirs_directories)
    if watch_dirs_refresh_interval_seconds is not None:
        wd_section["refresh_interval_seconds"] = float(watch_dirs_refresh_interval_seconds)
    result["watch_dirs"] = wd_section

    ca_section = copy.deepcopy(CODE_ANALYSIS_CONFIG_DEFAULTS)
    existing = result.get("code_analysis")
    if isinstance(existing, dict):
        ca_section = _deep_merge_dict(ca_section, existing)
    if code_analysis is not None:
        if not isinstance(code_analysis, dict):
            raise TypeError("code_analysis must be a dict when provided")
        ca_section = _deep_merge_dict(ca_section, code_analysis)

    if code_analysis_enabled is not None:
        ca_section["enabled"] = bool(code_analysis_enabled)
    if code_analysis_protocol is not None:
        ca_section["protocol"] = str(code_analysis_protocol).strip()
    if code_analysis_host is not None:
        ca_section["host"] = str(code_analysis_host).strip()
    if code_analysis_port is not None:
        ca_section["port"] = int(code_analysis_port)
    if code_analysis_jsonrpc_path is not None:
        ca_section["jsonrpc_path"] = str(code_analysis_jsonrpc_path).strip()
    if code_analysis_timeout_seconds is not None:
        ca_section["timeout_seconds"] = float(code_analysis_timeout_seconds)
    if code_analysis_watch_dir_index is not None:
        ca_section["watch_dir_index"] = int(code_analysis_watch_dir_index)

    ssl_updates: Dict[str, Any] = {}
    if code_analysis_ssl_cert is not None:
        ssl_updates["cert"] = code_analysis_ssl_cert
    if code_analysis_ssl_key is not None:
        ssl_updates["key"] = code_analysis_ssl_key
    if code_analysis_ssl_ca is not None:
        ssl_updates["ca"] = code_analysis_ssl_ca
    if code_analysis_ssl_crl is not None:
        ssl_updates["crl"] = code_analysis_ssl_crl
    if code_analysis_ssl_dnscheck is not None:
        ssl_updates["dnscheck"] = bool(code_analysis_ssl_dnscheck)
    if code_analysis_ssl_check_hostname is not None:
        ssl_updates["check_hostname"] = bool(code_analysis_ssl_check_hostname)
    if ssl_updates:
        ssl_block = ca_section.get("ssl")
        if not isinstance(ssl_block, dict):
            ssl_block = {}
        ssl_block.update(ssl_updates)
        ca_section["ssl"] = ssl_block

    if str(ca_section.get("protocol", "https")).lower() == "http":
        ca_section["ssl"] = None

    result["code_analysis"] = ca_section

    td_updates: Dict[str, Any] = {}
    if terminal_defaults_workspace_write is not None:
        td_updates["workspace_write"] = bool(terminal_defaults_workspace_write)
    if terminal_defaults_pid_namespace is not None:
        td_updates["pid_namespace"] = str(terminal_defaults_pid_namespace).strip().lower()
    if terminal_defaults_keep_container is not None:
        td_updates["keep_container"] = bool(terminal_defaults_keep_container)
    if td_updates:
        term = result.setdefault("terminal", {})
        if not isinstance(term, dict):
            term = {}
            result["terminal"] = term
        defaults_block = term.setdefault("defaults", copy.deepcopy(TERMINAL_DEFAULTS_CONFIG))
        if not isinstance(defaults_block, dict):
            defaults_block = copy.deepcopy(TERMINAL_DEFAULTS_CONFIG)
            term["defaults"] = defaults_block
        defaults_block.update(td_updates)

    if overrides:
        for key, value in overrides.items():
            result[key] = copy.deepcopy(value)

    errors = validate_terminal_config(result)
    if errors:
        lines = "; ".join(f"{e.field}: {e.message}" for e in errors)
        raise ValueError(f"Generated config failed validate_terminal_config: {lines}")
    return result
