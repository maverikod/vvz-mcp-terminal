"""
PID namespace mode for session sandbox containers.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

PID_NAMESPACE_CONTAINER = "container"
PID_NAMESPACE_HOST = "host"
VALID_PID_NAMESPACES = frozenset({PID_NAMESPACE_CONTAINER, PID_NAMESPACE_HOST})


def normalize_pid_namespace(value: Optional[str], *, default: str = PID_NAMESPACE_CONTAINER) -> str:
    """Return a validated pid_namespace string."""
    if value is None or str(value).strip() == "":
        return default
    mode = str(value).strip().lower()
    if mode not in VALID_PID_NAMESPACES:
        raise ValueError(
            f"pid_namespace must be one of {sorted(VALID_PID_NAMESPACES)}, got {value!r}"
        )
    return mode


def apply_docker_pid_namespace(cmd: List[str], pid_namespace: str) -> None:
    """Append ``--pid=host`` to a docker run argv when requested."""
    if pid_namespace == PID_NAMESPACE_HOST:
        logger.warning(
            "pid_namespace=host grants container access to the host PID namespace "
            "(read /proc, send signals). Use only in development/debug environments."
        )
        cmd.append("--pid=host")
