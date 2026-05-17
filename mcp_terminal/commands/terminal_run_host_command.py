"""
terminal_run_host: run allowlisted commands on the host (not in Docker).

Requires ``terminal.host_execution.enabled`` and a non-empty ``allowed_commands`` list.
Use ``terminal_run`` for sandbox container execution.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Optional, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.commands.session_resolve import resolve_session
from mcp_terminal.commands.terminal_run_host_metadata import get_terminal_run_host_metadata
from mcp_terminal.commands.terminal_run_host_schema import get_terminal_run_host_schema
from mcp_terminal.runtime_context import get_session_store, registry_resolve_project
from mcp_terminal.services.host_run_service import enqueue_host_terminal_run
from mcp_terminal.services.shell_state import resolve_cwd, resolve_use_venv

_DEFAULT_TIMEOUT_S: int = 600


class TerminalRunHostCommand(Command):
    """Queue host-side command execution for an existing session."""

    name: ClassVar[str] = "terminal_run_host"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = (
        "Run an allowlisted command on the host (outside Docker). Requires "
        "terminal.host_execution.enabled in server config. Returns job_id and seq; "
        "poll terminal_get_status."
    )
    category: ClassVar[str] = "custom"
    author: ClassVar[str] = "Vasiliy Zdanovskiy"
    email: ClassVar[str] = "vasilyvz@gmail.com"
    result_class: ClassVar[Type[CommandResult]] = CommandResult

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return get_terminal_run_host_schema()

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", "")).strip()
        session_id = str(kwargs.get("session_id", "")).strip()
        execution_kind = str(kwargs.get("execution_kind", "")).strip()
        command = kwargs.get("command")
        argv = kwargs.get("argv")
        cwd = kwargs.get("cwd")
        timeout_seconds = int(kwargs.get("timeout_seconds", _DEFAULT_TIMEOUT_S))
        use_venv_arg: Optional[bool] = (
            bool(kwargs["use_venv"]) if "use_venv" in kwargs else None
        )

        if execution_kind not in ("shell", "argv"):
            return CommandResult(success=False, error="INVALID_COMMAND")

        cmd_str: Optional[str] = None
        if command is not None:
            cmd_str = str(command).strip()
        argv_list: Optional[List[str]] = None
        if argv is not None:
            if not isinstance(argv, list):
                return CommandResult(success=False, error="INVALID_COMMAND")
            argv_list = [str(x) for x in argv]

        resolved = registry_resolve_project(project_id)
        if not resolved.success or resolved.project_dir is None:
            return CommandResult(
                success=False,
                error=resolved.error_code or "PROJECT_NOT_FOUND",
            )

        srec, sess_err = resolve_session(project_id, session_id)
        if sess_err is not None or srec is None:
            return CommandResult(success=False, error=sess_err or "INVALID_SESSION")

        effective_cwd, cwd_err = resolve_cwd(srec.session_dir, cwd)
        if cwd_err is not None or effective_cwd is None:
            return CommandResult(success=False, error=cwd_err or "INVALID_CWD")

        use_venv = resolve_use_venv(srec.session_dir, use_venv_arg)
        session_store = get_session_store()

        return await enqueue_host_terminal_run(
            project_id=project_id,
            session_id=session_id,
            srec=srec,
            execution_kind=execution_kind,
            cmd_str=cmd_str,
            argv_list=argv_list,
            effective_cwd=effective_cwd,
            timeout_seconds=timeout_seconds,
            use_venv=use_venv,
            project_dir=resolved.project_dir,
            session_store=session_store,
        )

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_terminal_run_host_metadata(cls)
