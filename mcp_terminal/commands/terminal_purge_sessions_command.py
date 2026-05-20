"""
terminal_purge_sessions: global purge of session dirs (config-gated).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.cli_sessions_purge import purge_all_terminal_sessions
from mcp_terminal.commands.terminal_purge_sessions_metadata import (
    get_terminal_purge_sessions_metadata,
)
from mcp_terminal.commands.terminal_purge_sessions_schema import (
    get_terminal_purge_sessions_schema,
)
from mcp_terminal.errors import ErrorCode
from mcp_terminal.services.terminal_admin_config import purge_sessions_allowed
from mcp_terminal.term_config import default_config_path


class TerminalPurgeSessionsCommand(Command):
    """Run the same purge as ``termgr purge-sessions`` when config allows."""

    name: ClassVar[str] = "terminal_purge_sessions"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = (
        "Purge all .terminals session dirs under watch anchors (and optionally Docker "
        "sandboxes). Requires terminal.admin.allow_purge_sessions in server config."
    )
    category: ClassVar[str] = "custom"
    author: ClassVar[str] = "Vasiliy Zdanovskiy"
    email: ClassVar[str] = "vasilyvz@gmail.com"
    result_class: ClassVar[Type[CommandResult]] = CommandResult

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return get_terminal_purge_sessions_schema()

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        if not purge_sessions_allowed():
            return CommandResult(success=False, error=ErrorCode.PURGE_SESSIONS_DISABLED)

        dry_run = bool(kwargs.get("dry_run", False))
        kill_docker = bool(kwargs.get("kill_docker", True))
        remove_runtime = bool(kwargs.get("remove_runtime", False))

        cfg = default_config_path()
        if not cfg.is_file():
            return CommandResult(success=False, error="INVALID_CONFIG")

        report = purge_all_terminal_sessions(
            cfg,
            dry_run=dry_run,
            kill_docker=kill_docker,
            remove_runtime=remove_runtime,
        )
        return CommandResult(
            success=True,
            data={
                "containers_killed": report.containers_killed,
                "session_dirs_removed": report.session_dirs_removed,
                "empty_terminals_trees_removed": report.terminals_trees_removed,
                "runtime_dirs_removed": report.runtime_dirs_removed,
                "memory_sessions_dropped": report.memory_sessions_dropped,
                "errors": list(report.errors),
            },
        )

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_terminal_purge_sessions_metadata(cls)
