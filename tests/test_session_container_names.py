"""Tests for session container naming and spec fingerprint."""

from __future__ import annotations

from pathlib import Path

from mcp_terminal.services.container_runner import ContainerSpec
from mcp_terminal.services.sandbox_policy import MountSpec
from mcp_terminal.services.session_container import (
    session_container_name,
    spec_fingerprint,
)


def test_session_container_name_stable() -> None:
    pid = "00000000-0000-4000-8000-000000000001"
    sid = "00000000-0000-4000-8000-000000000002"
    a = session_container_name(pid, sid)
    b = session_container_name(pid, sid)
    assert a == b
    assert a.startswith("mcp-term-")


def test_spec_fingerprint_changes_with_readonly() -> None:
    base = MountSpec(
        workspace_source=Path("/tmp/ws"),
        workspace_readonly=True,
        scratch_enabled=True,
        workdir="/workspace",
        mode="read_only",
    )
    spec_ro = ContainerSpec(
        image="img:1",
        mount_spec=base,
        network_spec="none",
        user="1000:1000",
        memory_limit="512m",
        cpu_limit=1.0,
        pids_limit=256,
        timeout_seconds=60,
    )
    spec_rw = ContainerSpec(
        image="img:1",
        mount_spec=MountSpec(
            workspace_source=Path("/tmp/ws"),
            workspace_readonly=False,
            scratch_enabled=True,
            workdir="/workspace",
            mode="workspace_write",
        ),
        network_spec="none",
        user="1000:1000",
        memory_limit="512m",
        cpu_limit=1.0,
        pids_limit=256,
        timeout_seconds=60,
    )
    assert spec_fingerprint(spec_ro) != spec_fingerprint(spec_rw)
