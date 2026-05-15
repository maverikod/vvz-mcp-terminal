"""
terminal_kill command for mcp_terminal (C-014).

Sends SIGKILL to the in-process ``docker run`` subprocess for a pending command
(same semantics as ``kill -9`` on POSIX via ``subprocess.Popen.kill``).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.runtime_context import get_session_store
from mcp_terminal.services.command_history import CommandHistory
from mcp_terminal.services.running_terminal_jobs import kill as kill_running


class TerminalKillCommand(Command):
    """MCP command: terminal_kill — SIGKILL the sandbox subprocess for one seq."""

    name: ClassVar[str] = "terminal_kill"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = (
        "Send SIGKILL to the running terminal command subprocess (docker run client) "
        "for the given session seq when status is still pending. "
        "Poll terminal_get_status afterward; exit_code may reflect signal termination."
    )
    category: ClassVar[str] = "custom"
    author: ClassVar[str] = "Vasiliy Zdanovskiy"
    email: ClassVar[str] = "vasilyvz@gmail.com"
    result_class: ClassVar[Type[CommandResult]] = CommandResult

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID4; must match the session.",
                },
                "session_id": {"type": "string", "description": "Session UUID4."},
                "seq": {
                    "type": "integer",
                    "description": "Session-local command sequence number to kill.",
                },
            },
            "required": ["project_id", "session_id", "seq"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", "")).strip()
        session_id = str(kwargs.get("session_id", "")).strip()
        try:
            seq = int(kwargs.get("seq", 0))
        except (TypeError, ValueError):
            return CommandResult(success=False, error="INVALID_SEQ")
        if seq < 1:
            return CommandResult(success=False, error="INVALID_SEQ")

        session_store = get_session_store()
        srec = session_store.get_session(session_id)
        if srec is None or srec.project_id != project_id:
            return CommandResult(success=False, error="INVALID_SESSION")

        session_store.touch_activity(session_id)
        history = CommandHistory(srec.session_dir)
        all_records = history.list_records(limit=10000)
        cmd_record = next((r for r in all_records if r.seq == seq), None)
        if cmd_record is None:
            return CommandResult(success=False, error="NOT_FOUND")
        if cmd_record.status != "pending":
            return CommandResult(success=False, error="NOT_RUNNING")

        sent = kill_running(session_id, seq)
        if not sent:
            return CommandResult(
                success=False,
                error="KILL_NOT_APPLIED",
                data={
                    "detail": (
                        "No active subprocess was registered for this seq "
                        "(already finished or not yet started)."
                    ),
                },
            )
        return CommandResult(
            success=True,
            data={
                "session_id": session_id,
                "seq": seq,
                "killed": True,
                "signal": "SIGKILL",
            },
        )
