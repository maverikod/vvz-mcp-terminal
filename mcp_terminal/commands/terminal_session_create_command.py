"""
terminal_session_create command for mcp_terminal (C-014, C-005).

``session_id`` and ``project_id`` are external UUID4 values (from the AI editor).
Composite key (project_id, session_id) is unique. Runtime bootstrap is queued.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar, Dict, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult
from mcp_proxy_adapter.core.job_manager import enqueue_coroutine

from mcp_terminal.jobs.session_bootstrap_job import SessionBootstrapJob, SessionBootstrapJobParams
from mcp_terminal.runtime_context import registry_resolve_project, get_session_store
from mcp_terminal.services.session_bootstrap import write_bootstrap_pending
from mcp_terminal.commands.terminal_session_create_metadata import (
    get_terminal_session_create_metadata,
)
from mcp_terminal.services.session_ids import validate_uuid4_field

_SESSION_CREATE_PYTHON_REMINDER = (
    "terminal_run persists cwd in .terminals/<session_id>/shell_state.json. "
    "Use keep_container:true for multi-step work. "
    "For Python prefer /workspace/.venv/bin/python or "
    "'source .venv/bin/activate && …' in one shell command."
)


class TerminalSessionCreateCommand(Command):
    """Create or return an existing terminal session (C-005)."""

    name: ClassVar[str] = "terminal_session_create"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = (
        "Open a terminal session for (project_id, session_id) from the editor. "
        "Both must be UUID4. If the pair already exists, returns already_exists. "
        "Only one session per project has workspace write; others are read-only on "
        "/workspace. Bootstrap is queued when bootstrap_python_env is true."
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
                    "description": "Project UUID4 from the editor; must exist in registry.",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session UUID4 from the editor; unique with project_id.",
                },
                "bootstrap_python_env": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "When true (default): enqueue Docker image build/verify under "
                        ".mcp_terminal/runtime/ when requirements.txt exists."
                    ),
                },
                "bootstrap_timeout_seconds": {
                    "type": "integer",
                    "default": 1200,
                    "minimum": 60,
                    "maximum": 7200,
                    "description": "Timeout for docker build / verify in the bootstrap queue job.",
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
            "required": ["project_id", "session_id"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", "")).strip()
        session_id = str(kwargs.get("session_id", "")).strip()
        for field, value in (("project_id", project_id), ("session_id", session_id)):
            err = validate_uuid4_field(value, field)
            if err:
                return CommandResult(success=False, error=err)

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
        rec, created, ensure_err = session_store.ensure_session(
            project_id=project_id,
            session_id=session_id,
            project_dir=resolved.project_dir,
        )
        if ensure_err is not None or rec is None:
            return CommandResult(success=False, error=ensure_err or "INVALID_SESSION")

        data: Dict[str, Any] = {
            "session_id": rec.session_id,
            "project_id": rec.project_id,
            "created": created,
            "already_exists": not created,
            "workspace_write": rec.workspace_write,
            "created_at": rec.created_at.isoformat(),
            "reminder": _SESSION_CREATE_PYTHON_REMINDER,
        }
        if bootstrap:
            job_params = SessionBootstrapJobParams(
                project_id=rec.project_id,
                session_id=rec.session_id,
                project_dir=rec.project_dir,
                session_dir=rec.session_dir,
                image_profile=image_profile,
                timeout_seconds=timeout_s,
            )
            job = SessionBootstrapJob(job_params)

            async def _run_bootstrap() -> dict:
                return await asyncio.to_thread(job.run)

            bootstrap_job_id = enqueue_coroutine(_run_bootstrap())
            write_bootstrap_pending(rec.session_dir, job_id=bootstrap_job_id)
            data["bootstrap"] = {
                "status": "pending",
                "job_id": bootstrap_job_id,
            }
        return CommandResult(success=True, data=data)

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_terminal_session_create_metadata(cls)
