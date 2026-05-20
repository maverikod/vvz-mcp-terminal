"""
terminal_get_session_bootstrap command for mcp_terminal (C-014, C-005).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.commands.session_resolve import resolve_session
from mcp_terminal.commands.terminal_get_session_bootstrap_metadata import (
    get_terminal_get_session_bootstrap_metadata,
)
from mcp_terminal.runtime_context import get_session_store
from mcp_terminal.services.session_bootstrap import read_bootstrap_state


class TerminalGetSessionBootstrapCommand(Command):
    """Return runtime-image bootstrap state from ``bootstrap.json`` for a session."""

    name: ClassVar[str] = "terminal_get_session_bootstrap"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = (
        "Return bootstrap status for a session (pending, completed, or failed). "
        "Poll after terminal_session_create when bootstrap_python_env is true."
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
                "project_id": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["project_id", "session_id"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", "")).strip()
        session_id = str(kwargs.get("session_id", "")).strip()
        record, err = resolve_session(project_id, session_id)
        if err is not None:
            return CommandResult(success=False, error=err)
        session_store = get_session_store()
        session_store.touch_activity(record.project_id, record.session_id)
        state = read_bootstrap_state(record.session_dir)
        if state is None:
            return CommandResult(success=False, error="NOT_FOUND")
        runtime = state.get("runtime_image")
        if not isinstance(runtime, dict):
            return CommandResult(success=False, error="BOOTSTRAP_STATE_CORRUPT")
        return CommandResult(success=True, data={"runtime_image": runtime})

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_terminal_get_session_bootstrap_metadata(cls)
