"""
terminal_session_create command for mcp_terminal (C-014, C-005).

``session_id`` and ``project_id`` are external UUID4 values (from the AI editor).
Composite key (project_id, session_id) is unique. Runtime bootstrap is queued.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar, Dict, Optional, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult
from mcp_proxy_adapter.core.job_manager import enqueue_coroutine

from mcp_terminal.jobs.session_bootstrap_job import SessionBootstrapJob, SessionBootstrapJobParams
from mcp_terminal.runtime_context import registry_resolve_project, get_session_store
from mcp_terminal.services.session_bootstrap import write_bootstrap_pending
from mcp_terminal.commands.terminal_session_create_metadata import (
    get_terminal_session_create_metadata,
)
from mcp_terminal.services.session_ids import validate_uuid4_field
from mcp_terminal.services.shell_state import (
    ShellState,
    read_shell_state,
    resolve_use_venv,
    write_shell_state,
)
from mcp_terminal.services.pid_namespace import normalize_pid_namespace
from mcp_terminal.services.venv_activation import WORKSPACE_VENV_ROOT, project_has_usable_venv

_SESSION_CREATE_PYTHON_REMINDER = (
    "terminal_run puts /workspace/.venv/bin on PATH automatically when use_venv is true "
    "(default if the project has .venv). No source activate. "
    "Use keep_container:true for multi-step work. "
    "Set use_venv:false on session create or terminal_run to use system tools only."
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
                "workspace_write": {
                    "type": "boolean",
                    "description": (
                        "Whether this session may mount /workspace read-write. "
                        "Omitted: terminal.defaults.workspace_write from term server config. "
                        "At most one session per project may be true."
                    ),
                },
                "use_venv": {
                    "type": "boolean",
                    "description": (
                        "Prepends /workspace/.venv/bin to PATH on terminal_run (no activate). "
                        "Omitted: terminal.defaults.use_venv from term server config."
                    ),
                },
                "pid_namespace": {
                    "type": "string",
                    "enum": ["container", "host"],
                    "description": (
                        "Docker PID namespace for this session. "
                        "Omitted: terminal.defaults.pid_namespace from term server config."
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

        workspace_write_create: Optional[bool] = None
        if "workspace_write" in kwargs:
            workspace_write_create = bool(kwargs["workspace_write"])

        use_venv_create: Optional[bool] = None
        if "use_venv" in kwargs:
            use_venv_create = bool(kwargs["use_venv"])

        pid_namespace_create: Optional[str] = None
        if "pid_namespace" in kwargs:
            try:
                pid_namespace_create = normalize_pid_namespace(kwargs.get("pid_namespace"))
            except ValueError:
                return CommandResult(success=False, error="INVALID_PID_NAMESPACE")

        session_store = get_session_store()
        rec, created, ensure_err = session_store.ensure_session(
            project_id=project_id,
            session_id=session_id,
            project_dir=resolved.project_dir,
            use_venv=use_venv_create,
            pid_namespace=pid_namespace_create,
            workspace_write=workspace_write_create,
        )
        if ensure_err is not None or rec is None:
            return CommandResult(success=False, error=ensure_err or "INVALID_SESSION")

        if not created and use_venv_create is not None:
            state = read_shell_state(rec.session_dir)
            if state.use_venv != use_venv_create:
                write_shell_state(
                    rec.session_dir,
                    ShellState(
                        cwd=state.cwd,
                        container_id=state.container_id,
                        container_name=state.container_name,
                        spec_fingerprint=state.spec_fingerprint,
                        use_venv=use_venv_create,
                    ),
                )

        if not created and pid_namespace_create is not None and rec.pid_namespace != pid_namespace_create:
            rec.pid_namespace = pid_namespace_create
            session_store.persist_session_record(rec)

        has_venv = project_has_usable_venv(resolved.project_dir)
        use_venv = resolve_use_venv(rec.session_dir, use_venv_create)

        data: Dict[str, Any] = {
            "session_id": rec.session_id,
            "project_id": rec.project_id,
            "created": created,
            "already_exists": not created,
            "workspace_write": rec.workspace_write,
            "created_at": rec.created_at.isoformat(),
            "venv_ready": has_venv,
            "use_venv": use_venv,
            "pid_namespace": rec.pid_namespace,
            "python": f"{WORKSPACE_VENV_ROOT}/bin/python" if has_venv and use_venv else None,
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
