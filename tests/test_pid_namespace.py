"""PID namespace docker flags."""

from __future__ import annotations

import pytest

from mcp_terminal.services.container_runner import ContainerRunner, ContainerSpec
from mcp_terminal.services.pid_namespace import (
    PID_NAMESPACE_CONTAINER,
    PID_NAMESPACE_HOST,
    apply_docker_pid_namespace,
    normalize_pid_namespace,
)
from mcp_terminal.services.sandbox_policy import MountSpec
from pathlib import Path


def test_normalize_pid_namespace_defaults() -> None:
    assert normalize_pid_namespace(None) == PID_NAMESPACE_CONTAINER
    assert normalize_pid_namespace("host") == PID_NAMESPACE_HOST


def test_normalize_pid_namespace_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        normalize_pid_namespace("pod")


def test_build_cmd_includes_pid_host() -> None:
    mount = MountSpec(
        workspace_source=Path("/tmp/ws"),
        workspace_readonly=True,
        scratch_enabled=True,
        workdir="/workspace",
        mode="read_only",
    )
    spec = ContainerSpec(
        image="python:3.12",
        mount_spec=mount,
        network_spec="none",
        user="1000:1000",
        memory_limit="512m",
        cpu_limit=1.0,
        pids_limit=256,
        timeout_seconds=60,
        resolved_argv=["true"],
        pid_namespace=PID_NAMESPACE_HOST,
    )
    cmd = ContainerRunner().build_cmd(spec)
    assert "--pid=host" in cmd


def test_build_cmd_container_mode_omits_pid_host() -> None:
    mount = MountSpec(
        workspace_source=Path("/tmp/ws"),
        workspace_readonly=True,
        scratch_enabled=True,
        workdir="/workspace",
        mode="read_only",
    )
    spec = ContainerSpec(
        image="python:3.12",
        mount_spec=mount,
        network_spec="none",
        user="1000:1000",
        memory_limit="512m",
        cpu_limit=1.0,
        pids_limit=256,
        timeout_seconds=60,
        resolved_argv=["true"],
        pid_namespace=PID_NAMESPACE_CONTAINER,
    )
    cmd = ContainerRunner().build_cmd(spec)
    assert "--pid=host" not in cmd


def test_apply_docker_pid_namespace_appends_flag() -> None:
    cmd = ["docker", "run"]
    apply_docker_pid_namespace(cmd, PID_NAMESPACE_HOST)
    assert cmd[-1] == "--pid=host"
