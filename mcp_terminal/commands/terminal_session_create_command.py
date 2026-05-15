"""
terminal_session_create command for mcp_terminal (C-014, C-005).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult

from mcp_terminal.runtime_context import registry_resolve_project, get_session_store
from mcp_terminal.services.session_bootstrap import run_session_runtime_bootstrap

_SESSION_CREATE_PYTHON_REMINDER = (
    "To run project Python, activate .venv in the same shell line as your command "
    "(e.g. . .venv/bin/activate && python …) or invoke /workspace/.venv/bin/python "
    "directly. Each terminal_run is a separate process; activation does not persist "
    "across runs."
)


class TerminalSessionCreateCommand(Command):
    """Create a new terminal session under a resolved project (C-005)."""

    name: ClassVar[str] = "terminal_session_create"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = "Create a new terminal session for a project."
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
                    "description": "Project UUID4; must exist in the server project registry.",
                },
                "bootstrap_python_env": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "When true (default): once per session open, ensure a per-project Docker "
                        "image under .mcp_terminal/runtime/ when requirements.txt exists "
                        "(docker build + image_state.json). Not repeated on each terminal_run."
                    ),
                },
                "bootstrap_timeout_seconds": {
                    "type": "integer",
                    "default": 1200,
                    "minimum": 60,
                    "maximum": 7200,
                    "description": "Timeout for docker build / verify on session open.",
                },
                "image_profile": {
                    "type": "string",
                    "enum": ["python_dev_3_12", "node_dev_20", "base_tools"],
                    "default": "python_dev_3_12",
                    "description": (
                        "Used for runtime image recipe when bootstrap_python_env is true."
                    ),
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", "")).strip()
        bootstrap = bool(kwargs.get("bootstrap_python_env", True))
        raw_timeout = kwargs.get("bootstrap_timeout_seconds", 1200)
        try:
            timeout_s = int(raw_timeout)
        except (TypeError, ValueError):
            timeout_s = 1200
        timeout_s = max(60, min(7200, timeout_s))
        image_profile = str(kwargs.get("image_profile", "python_dev_3_12"))

        resolved = registry_resolve_project(project_id)
        if not resolved.success or resolved.project_dir is None:
            return CommandResult(
                success=False,
                error=resolved.error_code or "PROJECT_NOT_FOUND",
            )
        session_store = get_session_store()
        rec = session_store.create_session(project_id=project_id, project_dir=resolved.project_dir)
        data: Dict[str, Any] = {
            "session_id": rec.session_id,
            "project_id": rec.project_id,
            "created_at": rec.created_at.isoformat(),
            "reminder": _SESSION_CREATE_PYTHON_REMINDER,
        }
        if bootstrap:
            br = await asyncio.to_thread(
                run_session_runtime_bootstrap,
                rec.project_dir,
                project_id=rec.project_id,
                session_dir=rec.session_dir,
                image_profile=image_profile,
                timeout_seconds=timeout_s,
            )
            data["bootstrap"] = {
                "success": br.success,
                "ran": br.ran,
                "skipped": br.skipped,
                "exit_code": br.exit_code,
                "detail": br.detail,
            }
            if not br.success:
                session_store.delete_session(rec.session_id, force=True)
                return CommandResult(
                    success=False,
                    error="BOOTSTRAP_FAILED",
                    data={
                        **data,
                        "bootstrap": {
                            **data["bootstrap"],
                            "stderr_tail": br.stderr_tail,
                        },
                    },
                )
        return CommandResult(success=True, data=data)
