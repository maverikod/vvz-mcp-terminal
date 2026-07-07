"""
terminal_host_exec: run configured host commands on the real host via SSH.

Requires ``terminal.host_execution.enabled`` plus allowlist or full_access and ssh settings.
Use ``terminal_run`` for sandbox container execution.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import posixpath
from typing import Any, ClassVar, Dict, List, Optional, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.commands.session_resolve import resolve_session
from mcp_terminal.commands.terminal_host_exec_metadata import get_terminal_host_exec_metadata
from mcp_terminal.commands.terminal_host_exec_schema import get_terminal_host_exec_schema
from mcp_terminal.errors import ErrorCode
from mcp_terminal.runtime_context import get_session_store, registry_resolve_project
from mcp_terminal.services.host_run_service import enqueue_host_ssh_terminal_run
from mcp_terminal.services.shell_state import resolve_cwd, resolve_use_venv

_DEFAULT_TIMEOUT_S: int = 600


def _resolve_sessionless_host_cwd(cwd: Any) -> tuple[Optional[str], Optional[str]]:
    """Resolve sessionless host cwd without touching local/project paths."""
    if cwd is None or not str(cwd).strip():
        return "/root", None
    raw = str(cwd).strip()
    if "\x00" in raw:
        return None, ErrorCode.INVALID_CWD
    if not raw.startswith("/"):
        return None, ErrorCode.INVALID_CWD
    return posixpath.normpath(raw) or "/", None


class TerminalHostExecCommand(Command):
    """Queue real host-side command execution via SSH for an existing session."""

    name: ClassVar[str] = "terminal_host_exec"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = (
        "Run a configured command on the real host via SSH. Requires "
        "terminal.host_execution.enabled plus allowed_commands or full_access and ssh settings. "
        "Returns job_id and seq; poll terminal_get_status."
    )
    category: ClassVar[str] = "custom"
    author: ClassVar[str] = "Vasiliy Zdanovskiy"
    email: ClassVar[str] = "vasilyvz@gmail.com"
    result_class: ClassVar[Type[CommandResult]] = CommandResult

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return get_terminal_host_exec_schema()

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = super().validate_params(params)
        execution_kind = str(params.get("execution_kind", "")).strip()
        if execution_kind not in ("shell", "argv"):
            raise ValueError("execution_kind must be shell or argv")
        if execution_kind == "shell":
            cmd = params.get("command")
            if cmd is None or not str(cmd).strip():
                raise ValueError("command is required when execution_kind is shell")
        if execution_kind == "argv":
            argv = params.get("argv")
            if not isinstance(argv, list) or not argv:
                raise ValueError("argv is required when execution_kind is argv")
        return params

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", "")).strip()
        session_id = str(kwargs.get("session_id", "")).strip()
        execution_kind = str(kwargs.get("execution_kind", "")).strip()
        command = kwargs.get("command")
        argv = kwargs.get("argv")
        cwd = kwargs.get("cwd")
        target_user_raw = kwargs.get("target_user")
        timeout_seconds = int(kwargs.get("timeout_seconds", _DEFAULT_TIMEOUT_S))
        use_venv_arg: Optional[bool] = bool(kwargs["use_venv"]) if "use_venv" in kwargs else None

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

        target_user: Optional[str] = None
        if target_user_raw is not None and str(target_user_raw).strip():
            target_user = str(target_user_raw).strip()

        if bool(project_id) != bool(session_id):
            return CommandResult(success=False, error="INVALID_SESSION")

        if not project_id and not session_id:
            effective_cwd, cwd_err = _resolve_sessionless_host_cwd(cwd)
            if cwd_err is not None or effective_cwd is None:
                return CommandResult(success=False, error=cwd_err or "INVALID_CWD")
            return await enqueue_host_ssh_terminal_run(
                project_id="host",
                session_id="",
                srec=None,
                execution_kind=execution_kind,
                cmd_str=cmd_str,
                argv_list=argv_list,
                effective_cwd=effective_cwd,
                timeout_seconds=timeout_seconds,
                use_venv=bool(use_venv_arg) if use_venv_arg is not None else False,
                target_user=target_user,
                project_dir=None,
                session_store=None,
            )

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

        return await enqueue_host_ssh_terminal_run(
            project_id=project_id,
            session_id=session_id,
            srec=srec,
            execution_kind=execution_kind,
            cmd_str=cmd_str,
            argv_list=argv_list,
            effective_cwd=effective_cwd,
            timeout_seconds=timeout_seconds,
            use_venv=use_venv,
            target_user=target_user,
            project_dir=resolved.project_dir,
            session_store=session_store,
        )

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_terminal_host_exec_metadata(cls)
