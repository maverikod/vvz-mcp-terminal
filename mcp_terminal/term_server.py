"""
MCP Proxy Adapter HTTP server for mcp_terminal (HTTPS).

Registers terminal_* MCP commands via the adapter hook mechanism (C-014, C-016).
Existing adapter built-in and queue commands remain visible in MCP help.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from mcp_proxy_adapter.api.app import create_app
from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.command_registry import CommandRegistry
from mcp_proxy_adapter.commands.hooks import register_custom_commands_hook
from mcp_proxy_adapter.config import get_config
from mcp_proxy_adapter.core.app_factory.ssl_config import build_server_ssl_config
from mcp_proxy_adapter.core.server_engine import ServerEngineFactory
from mcp_terminal.commands.terminal_delete_command import TerminalDeleteCommand
from mcp_terminal.commands.terminal_get_command import TerminalGetCommand
from mcp_terminal.commands.terminal_get_session_bootstrap_command import (
    TerminalGetSessionBootstrapCommand,
)
from mcp_terminal.commands.terminal_get_status_command import TerminalGetStatusCommand
from mcp_terminal.commands.terminal_kill_command import TerminalKillCommand
from mcp_terminal.commands.terminal_list_command import TerminalListCommand
from mcp_terminal.commands.terminal_list_watch_command import TerminalListWatchCommand
from mcp_terminal.commands.terminal_read_command import TerminalReadCommand
from mcp_terminal.commands.terminal_run_command import TerminalRunCommand
from mcp_terminal.commands.terminal_run_host_command import TerminalRunHostCommand
from mcp_terminal.commands.terminal_search_commands_command import (
    TerminalSearchCommandsCommand,
)
from mcp_terminal.commands.terminal_search_output_command import (
    TerminalSearchOutputCommand,
)
from mcp_terminal.commands.terminal_session_create_command import (
    TerminalSessionCreateCommand,
)
from mcp_terminal.commands.terminal_sessions_command import TerminalSessionsCommand
from mcp_terminal.commands.terminal_stat_command import TerminalStatCommand
from mcp_terminal.commands.terminal_tail_command import TerminalTailCommand
from mcp_terminal.paths import repo_root
from mcp_terminal.runtime_context import set_terminal_services
from mcp_terminal.services.project_registry_refresh import (
    rebuild_project_registry,
    start_project_registry_refresh_daemon,
)
from mcp_terminal.services.session_store import SessionStore
from mcp_terminal.config.config_generator import generate_terminal_config
from mcp_terminal.services.host_execution_config import warn_if_host_execution_enabled_without_commands
from mcp_terminal.term_config import (
    DEFAULT_TERM_SERVER_LISTEN_PORT,
    load_validated_term_simple_config,
)

_SESSION_STORE = SessionStore()


def _install_project_registry(app_config: dict | None, config_path: Path | None) -> None:
    """Build ``ProjectRegistry`` from merged config + code-analysis anchor dirs."""
    path = (
        config_path if config_path is not None else (repo_root() / "configs" / "term_server.json")
    )
    reg = rebuild_project_registry(app_config or {}, config_path=path)
    set_terminal_services(session_store=_SESSION_STORE, project_registry=reg)


_install_project_registry({}, None)

_TERMINAL_COMMAND_TYPES: list[type[Command]] = [
    TerminalSessionsCommand,
    TerminalSessionCreateCommand,
    TerminalGetSessionBootstrapCommand,
    TerminalRunCommand,
    TerminalRunHostCommand,
    TerminalListCommand,
    TerminalListWatchCommand,
    TerminalGetCommand,
    TerminalReadCommand,
    TerminalSearchCommandsCommand,
    TerminalSearchOutputCommand,
    TerminalTailCommand,
    TerminalStatCommand,
    TerminalDeleteCommand,
    TerminalGetStatusCommand,
    TerminalKillCommand,
]


def _register_terminal_commands(registry: object) -> None:
    """Register all terminal_* commands via the adapter hook mechanism.

    Called by register_custom_commands_hook at adapter startup.
    No internal execution commands are exposed; only the terminal_* prefix
    commands are registered (C-014).

    Args:
        registry: The adapter command registry instance.
    """
    reg = cast(CommandRegistry, registry)
    for cmd_cls in _TERMINAL_COMMAND_TYPES:
        reg.register(cast(Any, cmd_cls), "custom")


register_custom_commands_hook(_register_terminal_commands)


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def main() -> None:
    """Load SimpleConfig, validate, create FastAPI app, run Hypercorn (HTTPS if configured)."""
    from mcp_terminal.repo_venv import ensure_repo_venv_interpreter

    ensure_repo_venv_interpreter()
    parser = argparse.ArgumentParser(description="MCP terminal minimal HTTPS server")
    parser.add_argument(
        "--config",
        type=str,
        default=str(repo_root() / "configs" / "term_server.json"),
        help="Path to SimpleConfig JSON (see mcp_terminal/term_server.defaults.json)",
    )
    args = parser.parse_args()

    cfg_path = Path(args.config).resolve()
    if not cfg_path.is_file():
        _die(f"Configuration file not found: {cfg_path}")

    try:
        app_config: dict = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        _die(f"Failed to read configuration: {exc}")

    try:
        simple_config, model = load_validated_term_simple_config(cfg_path)
    except ValueError as exc:
        _die(str(exc))
    for section, value in simple_config.to_dict().items():
        app_config[section] = value

    try:
        app_config = generate_terminal_config(app_config)
    except ValueError as exc:
        _die(str(exc))

    warn_if_host_execution_enabled_without_commands(app_config)

    _install_project_registry(app_config, cfg_path)

    app_config.setdefault("server", {})
    app_config["server"].setdefault("debug", False)
    app_config["server"].setdefault("log_level", "INFO")

    cfg = get_config()
    cfg.config_path = str(cfg_path)
    setattr(cfg, "model", model)
    cfg.config_data = app_config
    if hasattr(cfg, "feature_manager"):
        cfg.feature_manager.config_data = cfg.config_data

    watch_dirs_section = app_config.get("watch_dirs")
    interval = 60.0
    if isinstance(watch_dirs_section, dict):
        raw_iv = watch_dirs_section.get("refresh_interval_seconds", 60)
        if isinstance(raw_iv, (int, float)) and not isinstance(raw_iv, bool):
            interval = float(raw_iv)
    if interval > 0:

        def _app_config_snapshot() -> dict:
            data = getattr(get_config(), "config_data", None)
            return data if isinstance(data, dict) else {}

        start_project_registry_refresh_daemon(cfg_path, interval, _app_config_snapshot)

    app = create_app(
        title="MCP Terminal",
        description=(
            "Per-project sandboxed terminals: session-scoped Docker containers, "
            "shell_state.json for cwd, keep_container mode, terminal_* MCP commands."
        ),
        version="0.1.0",
        app_config=app_config,
        config_path=str(cfg_path),
    )

    host = str(app_config.get("server", {}).get("host", "127.0.0.1"))
    port = int(app_config.get("server", {}).get("port", DEFAULT_TERM_SERVER_LISTEN_PORT))

    server_config: dict = {
        "host": host,
        "port": port,
        "log_level": "info",
        "reload": False,
    }
    try:
        ssl_engine = build_server_ssl_config(app_config)
        if ssl_engine:
            server_config.update(ssl_engine)
    except ValueError as exc:
        _die(f"SSL configuration invalid: {exc}")

    engine = ServerEngineFactory.get_engine("hypercorn")
    assert engine is not None, "Hypercorn engine not available"
    engine.run_server(app, server_config)


if __name__ == "__main__":
    main()
