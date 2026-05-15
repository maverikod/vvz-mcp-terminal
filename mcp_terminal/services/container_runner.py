"""Container runtime for mcp_terminal sandbox execution (C-010).

Builds security-hardened container creation parameters and executes
containers with fixed /workspace mount, non-root user, and capability drop.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import subprocess  # noqa: F401
from dataclasses import dataclass, field
from pathlib import Path  # noqa: F401
from typing import Dict, FrozenSet, List, Optional  # noqa: F401

from mcp_terminal.services.sandbox_policy import MountSpec

logger = logging.getLogger(__name__)

# Fallback when host stat fails; bind mounts do not remap ownership.
_DEFAULT_BIND_MOUNT_USER = "65534:65534"


def workspace_bind_mount_user(workspace_source: Path) -> str:
    """Return ``uid:gid`` for ``docker run --user`` from the host project directory.

    Bind-mounted paths keep host ownership; running the container as the same
    ``uid:gid`` lets processes create files under ``/workspace`` (e.g. ``.venv``)
    without permission errors.
    """
    try:
        st = os.stat(workspace_source.resolve(), follow_symlinks=True)
    except OSError as exc:
        logger.warning(
            "workspace_bind_mount_user: stat failed for %s: %s",
            workspace_source,
            exc,
        )
        return _DEFAULT_BIND_MOUNT_USER
    return f"{st.st_uid}:{st.st_gid}"


@dataclass(frozen=True)
class ContainerSpec:
    """Security-hardened container creation parameters (C-010).

    Produced by ContainerRunner.build_spec(). Consumed by ContainerRunner.run().
    Encodes all mount, security, resource, and network settings in one
    immutable object.
    """

    image: str
    """Concrete server-side image reference (not caller-supplied name)."""
    mount_spec: MountSpec
    """Validated mount configuration from SandboxPolicy."""
    network_spec: str
    """Network mode string: 'none' or 'package_registry' egress config."""
    user: str
    """Host uid:gid for ``/workspace`` bind (e.g. ``1000:1000``); else ``65534:65534``."""
    memory_limit: str
    """Memory limit string for Docker/Podman, e.g. '1g'."""
    cpu_limit: float
    """CPU limit as a float, e.g. 1.0."""
    pids_limit: int
    """Maximum number of processes in the container."""
    timeout_seconds: int
    """Execution timeout in seconds."""
    environment: Dict[str, str] = field(default_factory=dict)
    """Safe minimal environment variables for the container."""
    resolved_argv: List[str] = field(default_factory=list)
    """Actual argv passed to the container entrypoint."""


class ContainerRunner:
    """Builds and executes security-hardened containers (C-010).

    All containers use /workspace as the fixed mount point. Forbidden options
    (--privileged, host namespaces, Docker socket) are never included
    regardless of the input.
    """

    _FORBIDDEN_DOCKER_OPTIONS: FrozenSet[str] = frozenset(
        {
            "--privileged",
            "--pid=host",
            "--pid host",
            "--network=host",
            "--network host",
            "--ipc=host",
            "--ipc host",
            "--uts=host",
            "--uts host",
            "/var/run/docker.sock",
        }
    )

    def __init__(self, *, runtime: str = "docker") -> None:
        """Initialise ContainerRunner.

        Args:
            runtime: Container runtime executable name ('docker' or 'podman').
        """
        self._runtime: str = runtime
        self._logger: logging.Logger = logging.getLogger(__name__)

    def build_cmd(self, spec: ContainerSpec) -> List[str]:
        """Build the docker/podman run command list from a ContainerSpec.

        The resulting command includes all security hardening flags.
        --privileged, host namespace flags, and Docker socket mounts are
        never included.

        Args:
            spec: Immutable container creation parameters.

        Returns:
            List of strings forming the complete docker/podman run command.
        """
        cmd: List[str] = [
            self._runtime,
            "run",
            "--rm",
            "--user",
            spec.user,
            "--workdir",
            spec.mount_spec.workdir,
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=256m",
            "--tmpfs",
            "/scratch:rw,noexec,nosuid,size=1g",
            "--pids-limit",
            str(spec.pids_limit),
            "--memory",
            spec.memory_limit,
            "--cpus",
            str(spec.cpu_limit),
            "--network",
            "none" if spec.network_spec == "none" else "bridge",
        ]
        ro = ":ro" if spec.mount_spec.workspace_readonly else ":rw"
        ws = spec.mount_spec.workspace_source
        cmd += ["-v", f"{ws}:/workspace{ro}"]
        for key, val in spec.environment.items():
            cmd += ["-e", f"{key}={val}"]
        cmd.append(spec.image)
        cmd.extend(spec.resolved_argv)
        return cmd
