"""Attach a PTY shell to an existing kept sandbox container."""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.commands.session_resolve import resolve_session
from mcp_terminal.commands.schema_common import schema_project_id, schema_session_id
from mcp_terminal.commands.terminal_interactive_metadata import (
    interactive_metadata,
    project_param,
    session_param,
)
from mcp_terminal.runtime_context import get_session_store
from mcp_terminal.services.interactive_shell import attach_shell, shell_status
from mcp_terminal.services.shell_state import normalize_cwd, read_shell_state


class TerminalAttachCommand(Command):
    """Attach a persistent interactive PTY to a kept sandbox container."""

    name: ClassVar[str] = "terminal_attach"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = "Attach an interactive PTY shell inside a kept sandbox container."
    category: ClassVar[str] = "custom"
    author: ClassVar[str] = "Vasiliy Zdanovskiy"
    email: ClassVar[str] = "vasilyvz@gmail.com"
    result_class: ClassVar[Type[CommandResult]] = CommandResult

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": schema_project_id(),
                "session_id": schema_session_id(),
                "command": {
                    "type": "string",
                    "enum": ["bash", "sh", "python", "ipython"],
                    "default": "bash",
                },
                "cols": {"type": "integer", "default": 120, "minimum": 20, "maximum": 400},
                "rows": {"type": "integer", "default": 30, "minimum": 5, "maximum": 120},
            },
            "required": ["project_id", "session_id"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", "")).strip()
        session_id = str(kwargs.get("session_id", "")).strip()
        command = str(kwargs.get("command", "bash")).strip() or "bash"
        cols = max(20, min(400, int(kwargs.get("cols", 120))))
        rows = max(5, min(120, int(kwargs.get("rows", 30))))
        if command not in {"bash", "sh", "python", "ipython"}:
            return CommandResult(success=False, error="INVALID_COMMAND")
        record, err = resolve_session(project_id, session_id)
        if err is not None:
            return CommandResult(success=False, error=err)
        get_session_store().touch_activity(record.project_id, record.session_id)
        state = read_shell_state(record.session_dir)
        cwd = normalize_cwd(state.cwd)
        container_cwd = "/workspace" if cwd == "." else f"/workspace/{cwd}"
        shell, shell_err = attach_shell(
            project_id=record.project_id,
            session_id=record.session_id,
            command=command,
            cwd=container_cwd,
            cols=cols,
            rows=rows,
        )
        if shell_err is not None or shell is None:
            return CommandResult(success=False, error=shell_err or "ATTACH_FAILED")
        return CommandResult(success=True, data=shell_status(shell))

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return interactive_metadata(
            cls,
            detailed_description=(
                "Attaches a server-managed pseudo-terminal to the existing kept sandbox "
                "container for this session. It does not start host execution and does "
                "not accept arbitrary container names or image references."
            ),
            parameters={
                "project_id": project_param(True),
                "session_id": session_param(True),
                "command": {
                    "description": "Interactive program to start inside the sandbox.",
                    "type": "string",
                    "required": False,
                    "enum": ["bash", "sh", "python", "ipython"],
                    "default": "bash",
                    "examples": ["bash", "python"],
                },
                "cols": {
                    "description": "PTY width in columns.",
                    "type": "integer",
                    "required": False,
                    "default": 120,
                    "examples": [120],
                },
                "rows": {
                    "description": "PTY height in rows.",
                    "type": "integer",
                    "required": False,
                    "default": 30,
                    "examples": [30],
                },
            },
            success_data={
                "shell_id": "Stable id used by send/read/resize/detach.",
                "running": "Whether the PTY process is still running.",
                "offset": "Current output offset.",
            },
            usage_examples=[
                {
                    "description": "Attach bash to a kept sandbox",
                    "command": {
                        "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                        "session_id": "46ce9394-01ca-4440-9c03-c4a7466c4ec5",
                    },
                }
            ],
        )
