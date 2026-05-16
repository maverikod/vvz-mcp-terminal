"""
terminal_run command for mcp_terminal (C-014, C-009).

Sandbox execution is **always** handed to the adapter job queue via
``enqueue_coroutine``; this handler returns immediately with ``job_id`` and
``seq``. Callers must not expect the container to finish in the same RPC turn.
Poll ``terminal_get_status`` (same ``project_id``, ``session_id``, ``seq``) and
read logs with ``terminal_tail`` / ``terminal_read``.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional, Type

from mcp_proxy_adapter.commands.base import Command, CommandResult
from mcp_proxy_adapter.core.job_manager import enqueue_coroutine

from mcp_terminal.jobs.terminal_execution_job import JobParams, TerminalExecutionJob
from mcp_terminal.commands.session_resolve import resolve_session
from mcp_terminal.runtime_context import registry_resolve_project, get_session_store
from mcp_terminal.services.command_history import CommandHistory, CommandRecord
from mcp_terminal.services.container_runner import ContainerSpec, workspace_bind_mount_user
from mcp_terminal.services.project_runtime_image import resolve_execution_image
from mcp_terminal.services.sandbox_policy import IMAGE_PROFILE_MAP, SandboxPolicy
from mcp_terminal.commands.terminal_run_metadata import get_terminal_run_metadata
from mcp_terminal.services.shell_state import resolve_cwd

_DEFAULT_TIMEOUT_S: int = 600


class TerminalRunCommand(Command):
    """Queue one terminal command execution inside the sandbox (C-009)."""

    name: ClassVar[str] = "terminal_run"
    version: ClassVar[str] = "1.0.0"
    descr: ClassVar[str] = (
        "Run a command in a session sandbox: start container, load shell_state.json "
        "(cwd), exec, save cwd, stop container unless keep_container is true. "
        "Returns job_id and seq immediately; poll terminal_get_status."
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
                "execution_kind": {"type": "string", "enum": ["shell", "argv"]},
                "command": {
                    "type": "string",
                    "description": "Shell command string when execution_kind is shell.",
                },
                "argv": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Argv list when execution_kind is argv.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Project-relative working directory inside /workspace.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["read_only", "workspace_write", "scratch_write"],
                    "default": "read_only",
                },
                "network": {
                    "type": "string",
                    "enum": ["none", "package_registry"],
                    "default": "none",
                },
                "image_profile": {
                    "type": "string",
                    "enum": ["python_dev_3_12", "node_dev_20", "base_tools"],
                    "default": "python_dev_3_12",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "default": _DEFAULT_TIMEOUT_S,
                    "minimum": 1,
                    "maximum": 86400,
                },
                "keep_container": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "When true, leave the session container running after the command "
                        "(for long multi-step work). When false (default), stop the container "
                        "after saving shell_state."
                    ),
                },
            },
            "required": ["project_id", "session_id", "execution_kind"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> CommandResult:
        kwargs.pop("context", None)
        project_id = str(kwargs.get("project_id", "")).strip()
        session_id = str(kwargs.get("session_id", "")).strip()
        execution_kind = str(kwargs.get("execution_kind", "")).strip()
        command = kwargs.get("command")
        argv = kwargs.get("argv")
        cwd = kwargs.get("cwd")
        keep_container = bool(kwargs.get("keep_container", False))
        mode = str(kwargs.get("mode", "read_only"))
        network = str(kwargs.get("network", "none"))
        image_profile = str(kwargs.get("image_profile", "python_dev_3_12"))
        timeout_seconds = int(kwargs.get("timeout_seconds", _DEFAULT_TIMEOUT_S))

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
        session_store = get_session_store()

        if mode == "workspace_write" and not srec.workspace_write:
            return CommandResult(success=False, error="WORKSPACE_WRITE_NOT_ALLOWED")

        effective_cwd, cwd_err = resolve_cwd(srec.session_dir, cwd)
        if cwd_err is not None or effective_cwd is None:
            return CommandResult(success=False, error=cwd_err or "INVALID_CWD")

        policy = SandboxPolicy()
        check = policy.validate(
            project_id=project_id,
            execution_kind=execution_kind,
            cwd=effective_cwd,
            mode=mode,
            network=network,
            image_profile=image_profile,
            command=cmd_str,
            argv=argv_list,
        )
        if not check.permitted:
            return CommandResult(success=False, error=check.error_code or "INVALID_COMMAND")

        mount, m_err = policy.build_mount_spec(
            workspace_source=resolved.project_dir,
            mode=mode,
            cwd=effective_cwd,
        )
        if m_err is not None or mount is None:
            return CommandResult(success=False, error=m_err.error_code if m_err else "INVALID_CWD")
        if not srec.workspace_write:
            mount = replace(mount, workspace_readonly=True)

        net, n_err = policy.build_network_spec(network)
        if n_err is not None or net is None:
            return CommandResult(
                success=False,
                error=n_err.error_code if n_err else "NETWORK_MODE_NOT_ALLOWED",
            )

        img_cmd, i_err = policy.build_image_and_command_spec(
            image_profile=image_profile,
            execution_kind=execution_kind,
            command=cmd_str,
            argv=argv_list,
        )
        if i_err is not None or img_cmd is None:
            return CommandResult(
                success=False, error=i_err.error_code if i_err else "INVALID_COMMAND"
            )

        stock = IMAGE_PROFILE_MAP.get(image_profile)
        if stock is None:
            return CommandResult(success=False, error="IMAGE_PROFILE_NOT_ALLOWED")
        exec_image, img_err = resolve_execution_image(
            resolved.project_dir,
            project_id=project_id,
            image_profile=image_profile,
            stock_image_ref=stock,
        )
        if img_err:
            return CommandResult(success=False, error=img_err)

        session_store.touch_activity(project_id, session_id)
        history = CommandHistory(srec.session_dir)
        seq = history.allocate_seq()
        stdout_file, stderr_file, meta_file = history.pre_create_output_files(seq)
        ts = datetime.now(timezone.utc).isoformat()
        record = CommandRecord(
            seq=seq,
            job_id=None,
            project_id=project_id,
            session_id=session_id,
            timestamp=ts,
            execution_kind=execution_kind,
            command=cmd_str if execution_kind == "shell" else None,
            argv=argv_list if execution_kind == "argv" else None,
            resolved_argv=list(img_cmd.resolved_argv),
            cwd=effective_cwd,
            mode=mode,
            network=network,
            image_profile=image_profile,
            status="pending",
            stdout_file=stdout_file,
            stderr_file=stderr_file,
            meta_file=meta_file,
        )
        history.append_record(record)

        container_spec = ContainerSpec(
            image=exec_image,
            mount_spec=mount,
            network_spec=network,
            user=workspace_bind_mount_user(mount.workspace_source),
            memory_limit="512m",
            cpu_limit=1.0,
            pids_limit=256,
            timeout_seconds=timeout_seconds,
            environment=dict(img_cmd.environment),
            resolved_argv=list(img_cmd.resolved_argv),
        )
        job_params = JobParams(
            project_id=project_id,
            session_id=session_id,
            seq=seq,
            session_dir=srec.session_dir,
            container_spec=container_spec,
            timeout_seconds=timeout_seconds,
            keep_container=keep_container,
            effective_cwd=effective_cwd,
            execution_kind=execution_kind,
            command=cmd_str if execution_kind == "shell" else None,
            argv=argv_list if execution_kind == "argv" else None,
        )
        job = TerminalExecutionJob(job_params)

        async def _run_sync() -> dict:
            return await asyncio.to_thread(job.run)

        # Invariant (C-009): never await job.run() here—only the adapter worker runs it.
        job_id = enqueue_coroutine(_run_sync())
        history.update_record(seq, status="pending", job_id=job_id)

        return CommandResult(
            success=True,
            data={
                "job_id": job_id,
                "seq": seq,
                "stdout_file": stdout_file,
                "stderr_file": stderr_file,
                "meta_file": meta_file,
                "cwd": effective_cwd,
                "keep_container": keep_container,
            },
        )

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_terminal_run_metadata(cls)
