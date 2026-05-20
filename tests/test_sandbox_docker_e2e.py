"""
Docker-gated E2E for tech_spec §21 sandbox MVP acceptance criteria.

Live-Docker §21 checks live here. Unit-testable §21 subset:
``tests/test_sandbox_mvp_acceptance.py``.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import uuid
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from mcp_terminal.commands.terminal_run_command import TerminalRunCommand
from mcp_terminal.jobs.terminal_execution_job import JobParams, TerminalExecutionJob
from mcp_terminal.services.audit_writer import session_audit_log_path
from mcp_terminal.services.command_history import CommandHistory
from mcp_terminal.services.container_runner import (
    ContainerRunner,
    ContainerSpec,
    workspace_bind_mount_user,
)
from mcp_terminal.services.sandbox_policy import IMAGE_PROFILE_MAP, SandboxPolicy
from mcp_terminal.services.session_container import (
    SessionContainerExecutor,
    _docker_inspect_running,
    session_container_name,
    stop_session_container,
)
from mcp_terminal.services.shell_state import ShellState, write_shell_state

_E2E_PROJECT_ID = "00000000-0000-4000-8000-00000000e2e1"
_E2E_IMAGE_CANDIDATES = (
    os.environ.get("MCP_TERMINAL_E2E_IMAGE", "").strip(),
    IMAGE_PROFILE_MAP["python_dev_3_12"],
    "bash:5.2",
)


def docker_available() -> bool:
    """True when ``docker`` is on PATH and ``docker info`` succeeds."""
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


_requires_docker = pytest.mark.skipif(
    not docker_available(),
    reason="Docker not available",
)


@lru_cache(maxsize=1)
def _resolve_e2e_image() -> str:
    """Pick a local image with ``bash`` for session exec scripts."""
    for raw in _E2E_IMAGE_CANDIDATES:
        if not raw:
            continue
        try:
            subprocess.run(
                ["docker", "image", "inspect", raw],
                capture_output=True,
                timeout=30,
                check=True,
            )
            return raw
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            continue
    pytest.skip("No E2E image on host; pull bash:5.2 or python-dev, or set MCP_TERMINAL_E2E_IMAGE")


def _container_spec(
    workspace: Path,
    *,
    mode: str,
    image: str,
    timeout_seconds: int = 60,
) -> ContainerSpec:
    mount, err = SandboxPolicy().build_mount_spec(
        workspace_source=workspace,
        mode=mode,
        cwd=".",
    )
    assert err is None and mount is not None
    return ContainerSpec(
        image=image,
        mount_spec=mount,
        network_spec="none",
        user=workspace_bind_mount_user(workspace),
        memory_limit="256m",
        cpu_limit=0.5,
        pids_limit=128,
        timeout_seconds=timeout_seconds,
        environment={
            "HOME": "/tmp/home",
            "TMPDIR": "/tmp",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
        },
        resolved_argv=[],
        pid_namespace="container",
    )


def _session_ids(suffix: str) -> tuple[str, str]:
    return _E2E_PROJECT_ID, str(uuid.uuid5(uuid.NAMESPACE_DNS, f"mcp-terminal-e2e-{suffix}"))


@pytest.fixture
def e2e_image() -> str:
    return _resolve_e2e_image()


@pytest.fixture
def e2e_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "project"
    ws.mkdir()
    return ws


def _teardown_container(project_id: str, session_id: str) -> None:
    stop_session_container(project_id, session_id)


def _volume_mounts_from_cmd(cmd: list[str]) -> list[str]:
    """Return ``-v`` bind-mount spec strings from a docker argv list."""
    mounts: list[str] = []
    for index, part in enumerate(cmd):
        if part == "-v" and index + 1 < len(cmd):
            mounts.append(cmd[index + 1])
    return mounts


@_requires_docker
def test_docker_build_cmd_read_only_mount_is_ro(e2e_workspace: Path, e2e_image: str) -> None:
    """§21: read_only mode produces a :ro workspace bind in the docker command."""
    spec = _container_spec(e2e_workspace, mode="read_only", image=e2e_image)
    cmd = ContainerRunner().build_cmd(spec)
    joined = " ".join(cmd)
    assert f"{e2e_workspace.resolve()}:/workspace:ro" in joined
    assert spec.mount_spec.workspace_readonly is True


@_requires_docker
def test_docker_read_only_blocks_workspace_write(e2e_workspace: Path, e2e_image: str) -> None:
    """§21: attempts to write in read_only mode fail inside the container."""
    project_id, session_id = _session_ids("ro-write")
    session_dir = e2e_workspace.parent / "session-ro"
    session_dir.mkdir()
    spec = _container_spec(e2e_workspace, mode="read_only", image=e2e_image)
    marker = e2e_workspace / "e2e_ro_marker"
    try:
        exit_code, timed_out, status = SessionContainerExecutor().run(
            project_id=project_id,
            session_id=session_id,
            seq=1,
            session_dir=session_dir,
            spec=spec,
            timeout_seconds=30,
            keep_container=False,
            effective_cwd=".",
            execution_kind="shell",
            command="touch /workspace/e2e_ro_marker",
            argv=None,
            use_venv=False,
        )
        assert timed_out is False
        assert status == "completed"
        assert exit_code != 0
        assert not marker.exists()
    finally:
        _teardown_container(project_id, session_id)


@_requires_docker
def test_docker_workspace_write_creates_file(e2e_workspace: Path, e2e_image: str) -> None:
    """§21: workspace_write mode can create a file inside the mounted project."""
    project_id, session_id = _session_ids("rw-write")
    session_dir = e2e_workspace.parent / "session-rw"
    session_dir.mkdir()
    spec = _container_spec(e2e_workspace, mode="workspace_write", image=e2e_image)
    marker = e2e_workspace / "e2e_rw_marker"
    try:
        exit_code, timed_out, status = SessionContainerExecutor().run(
            project_id=project_id,
            session_id=session_id,
            seq=1,
            session_dir=session_dir,
            spec=spec,
            timeout_seconds=30,
            keep_container=False,
            effective_cwd=".",
            execution_kind="shell",
            command="touch /workspace/e2e_rw_marker",
            argv=None,
            use_venv=False,
        )
        assert timed_out is False
        assert status == "completed"
        assert exit_code == 0
        assert marker.is_file()
    finally:
        _teardown_container(project_id, session_id)
        marker.unlink(missing_ok=True)


@_requires_docker
def test_docker_timeout_kills_long_sleep(e2e_workspace: Path, e2e_image: str) -> None:
    """§21: timeout works and cleans up the session container."""
    project_id, session_id = _session_ids("timeout")
    session_dir = e2e_workspace.parent / "session-timeout"
    session_dir.mkdir()
    spec = _container_spec(e2e_workspace, mode="read_only", image=e2e_image, timeout_seconds=60)
    name = session_container_name(project_id, session_id)
    try:
        exit_code, timed_out, status = SessionContainerExecutor().run(
            project_id=project_id,
            session_id=session_id,
            seq=1,
            session_dir=session_dir,
            spec=spec,
            timeout_seconds=2,
            keep_container=False,
            effective_cwd=".",
            execution_kind="argv",
            command=None,
            argv=["sleep", "60"],
            use_venv=False,
        )
        assert status == "completed"
        assert timed_out is True
        assert not _docker_inspect_running(name)
        assert exit_code is None or exit_code != 0
    finally:
        _teardown_container(project_id, session_id)


@_requires_docker
def test_docker_execution_job_writes_seq_output_files(e2e_workspace: Path, e2e_image: str) -> None:
    """§21: worker writes stdout/stderr seq log files (TerminalExecutionJob E2E)."""
    project_id, session_id = _session_ids("job-files")
    session_dir = e2e_workspace.parent / "session-job"
    session_dir.mkdir()
    history = CommandHistory(session_dir)
    seq = history.allocate_seq()
    stdout_file, stderr_file, meta_file = history.pre_create_output_files(seq)
    spec = _container_spec(e2e_workspace, mode="read_only", image=e2e_image)
    params = JobParams(
        project_id=project_id,
        session_id=session_id,
        seq=seq,
        session_dir=session_dir,
        project_dir=e2e_workspace,
        container_spec=spec,
        timeout_seconds=30,
        keep_container=False,
        effective_cwd=".",
        execution_kind="argv",
        command=None,
        argv=["echo", "e2e-stdout"],
        use_venv=False,
    )
    try:
        result = TerminalExecutionJob(params).run()
        assert result["status"] == "completed"
        assert result["timed_out"] is False
        prefix = CommandHistory.seq_to_prefix(seq)
        assert (session_dir / stdout_file).exists()
        assert (session_dir / stderr_file).exists()
        assert (session_dir / meta_file).exists()
        assert b"e2e-stdout" in (session_dir / f"{prefix}.stdout.log").read_bytes()
    finally:
        _teardown_container(project_id, session_id)


def _mock_enqueue_coroutine(coro, *, job_id: str = "e2e-sandbox-job") -> str:
    if asyncio.iscoroutine(coro):
        coro.close()
    return job_id


def test_terminal_run_queues_job_and_output_files(tmp_path: Path) -> None:
    """§21: terminal_run queues command and returns job_id, seq, output file names."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    write_shell_state(session_dir, ShellState(cwd=".", use_venv=False))
    project_id = _E2E_PROJECT_ID
    session_id = "00000000-0000-4000-8000-00000000e2e2"
    srec = SimpleNamespace(
        session_dir=session_dir,
        workspace_write=False,
        pid_namespace="container",
    )
    resolved = SimpleNamespace(success=True, project_dir=project_dir, error_code=None)
    session_store = SimpleNamespace(touch_activity=lambda *_a, **_k: None)

    cmd = TerminalRunCommand()
    with (
        patch(
            "mcp_terminal.commands.terminal_run_command.registry_resolve_project",
            return_value=resolved,
        ),
        patch(
            "mcp_terminal.commands.terminal_run_command.resolve_session",
            return_value=(srec, None),
        ),
        patch(
            "mcp_terminal.commands.terminal_run_command.get_session_store",
            return_value=session_store,
        ),
        patch(
            "mcp_terminal.commands.terminal_run_command.resolve_execution_image",
            return_value=(IMAGE_PROFILE_MAP["python_dev_3_12"], None),
        ),
        patch(
            "mcp_terminal.commands.terminal_run_command.TerminalExecutionJob",
            return_value=MagicMock(),
        ) as mock_job_cls,
        patch(
            "mcp_terminal.commands.terminal_run_command.enqueue_coroutine",
            side_effect=_mock_enqueue_coroutine,
        ),
    ):
        result = asyncio.run(
            cmd.execute(
                project_id=project_id,
                session_id=session_id,
                execution_kind="argv",
                argv=["true"],
                use_venv=False,
            )
        )

    assert result.success is True
    data = result.data
    assert data is not None
    assert data["job_id"] == "e2e-sandbox-job"
    seq = int(data["seq"])
    prefix = CommandHistory.seq_to_prefix(seq)
    assert data["stdout_file"] == f"{prefix}.stdout.log"
    assert data["stderr_file"] == f"{prefix}.stderr.log"
    assert data["meta_file"] == f"{prefix}.meta.json"
    assert (session_dir / data["stdout_file"]).exists()
    assert (session_dir / data["stderr_file"]).exists()
    assert (session_dir / data["meta_file"]).exists()
    mock_job_cls.assert_called_once()
    records = CommandHistory(session_dir).list_records()
    assert any(r.seq == seq and r.job_id == "e2e-sandbox-job" for r in records)


@_requires_docker
def test_docker_project_mounted_only_at_workspace(e2e_workspace: Path, e2e_image: str) -> None:
    """§21: project is mounted only at /workspace."""
    spec = _container_spec(e2e_workspace, mode="read_only", image=e2e_image)
    cmd = ContainerRunner().build_cmd(spec)
    mounts = _volume_mounts_from_cmd(cmd)
    workspace_mounts = [
        m for m in mounts if m.endswith(":/workspace:ro") or m.endswith(":/workspace:rw")
    ]
    assert len(workspace_mounts) == 1
    assert mounts == workspace_mounts
    assert mounts[0].startswith(f"{e2e_workspace.resolve()}:/workspace:")
    assert spec.mount_spec.workdir.startswith("/workspace")

    project_id, session_id = _session_ids("mount-only")
    session_dir = e2e_workspace.parent / "session-mount-only"
    session_dir.mkdir()
    marker = e2e_workspace / "e2e_mount_marker"
    marker.write_text("mounted", encoding="utf-8")
    try:
        exit_code, timed_out, status = SessionContainerExecutor().run(
            project_id=project_id,
            session_id=session_id,
            seq=1,
            session_dir=session_dir,
            spec=spec,
            timeout_seconds=30,
            keep_container=False,
            effective_cwd=".",
            execution_kind="shell",
            command="pwd && test -f /workspace/e2e_mount_marker",
            argv=None,
            use_venv=False,
        )
        assert timed_out is False
        assert status == "completed"
        assert exit_code == 0
    finally:
        _teardown_container(project_id, session_id)
        marker.unlink(missing_ok=True)


@_requires_docker
def test_docker_container_cannot_access_files_outside_mount(
    e2e_workspace: Path, e2e_image: str
) -> None:
    """§21: container cannot access files outside the mounted project."""
    outside = e2e_workspace.parent / "e2e_outside_secret.txt"
    outside.write_text("outside-secret", encoding="utf-8")
    project_id, session_id = _session_ids("outside-mount")
    session_dir = e2e_workspace.parent / "session-outside"
    session_dir.mkdir()
    spec = _container_spec(e2e_workspace, mode="read_only", image=e2e_image)
    try:
        exit_code, timed_out, status = SessionContainerExecutor().run(
            project_id=project_id,
            session_id=session_id,
            seq=1,
            session_dir=session_dir,
            spec=spec,
            timeout_seconds=30,
            keep_container=False,
            effective_cwd=".",
            execution_kind="shell",
            command=(
                "if test -r /workspace/../e2e_outside_secret.txt; then "
                "cat /workspace/../e2e_outside_secret.txt; exit 0; "
                "else exit 1; fi"
            ),
            argv=None,
            use_venv=False,
        )
        assert timed_out is False
        assert status == "completed"
        assert exit_code != 0
    finally:
        _teardown_container(project_id, session_id)
        outside.unlink(missing_ok=True)


@_requires_docker
def test_docker_every_run_has_audit_record(e2e_workspace: Path, e2e_image: str) -> None:
    """§21: every run has an audit record."""
    project_id, session_id = _session_ids("audit")
    session_dir = e2e_workspace.parent / "session-audit"
    session_dir.mkdir()
    history = CommandHistory(session_dir)
    seq = history.allocate_seq()
    stdout_file, stderr_file, meta_file = history.pre_create_output_files(seq)
    spec = _container_spec(e2e_workspace, mode="read_only", image=e2e_image)
    params = JobParams(
        project_id=project_id,
        session_id=session_id,
        seq=seq,
        session_dir=session_dir,
        project_dir=e2e_workspace,
        container_spec=spec,
        timeout_seconds=30,
        keep_container=False,
        effective_cwd=".",
        execution_kind="argv",
        command=None,
        argv=["echo", "e2e-audit"],
        use_venv=False,
    )
    audit_path = session_audit_log_path(session_dir)
    try:
        result = TerminalExecutionJob(params).run()
        assert result["status"] == "completed"
        assert audit_path.is_file()
        lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
        assert lines
        audit = json.loads(lines[-1])
        assert audit["seq"] == seq
        assert audit["project_id"] == project_id
        assert audit["session_id"] == session_id
        assert audit["execution_target"] == "sandbox"
        assert audit["stdout_file"] == stdout_file
        assert audit["stderr_file"] == stderr_file
        assert audit["policy_decision"] == "executed"
        assert audit["resolved_argv"] == ["echo", "e2e-audit"]
        assert (session_dir / meta_file).exists()
    finally:
        _teardown_container(project_id, session_id)
