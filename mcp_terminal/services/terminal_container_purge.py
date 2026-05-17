"""
Identify and remove Docker containers owned by mcp_terminal sandboxes.

Used by ``termgr purge-sessions``.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import subprocess
from typing import Set

from mcp_terminal.services.sandbox_policy import IMAGE_PROFILE_MAP

_SESSION_LABEL_VALUE = "true"
_SESSION_NAME_PREFIX = "mcp-term-"
_IMAGE_PREFIXES = (
    "mcp-terminal:pid-",
    "ghcr.io/mcp-terminal/",
)
_STOCK_IMAGES = frozenset(IMAGE_PROFILE_MAP.values())


def is_terminal_sandbox_container(
    *,
    image: str,
    names: str,
    session_label: str = "",
) -> bool:
    """True when a container belongs to terminal session sandboxes."""
    if session_label == _SESSION_LABEL_VALUE:
        return True
    for name in names.split(","):
        if name.strip().startswith(_SESSION_NAME_PREFIX):
            return True
    img = image.strip()
    if not img:
        return False
    base = img.split("@", 1)[0]
    if base in _STOCK_IMAGES:
        return True
    if base.startswith(_IMAGE_PREFIXES):
        return True
    return False


def remove_all_terminal_containers(*, dry_run: bool = False) -> int:
    """``docker rm -f`` every stopped or running terminal sandbox container."""
    try:
        fmt = '{{.ID}}\t{{.Image}}\t{{.Names}}\t{{.Label "mcp.terminal.session"}}'
        # Do not pass -q with --format: Docker ignores the template and prints IDs only.
        out = subprocess.check_output(
            ["docker", "ps", "-a", "--format", fmt],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
    except FileNotFoundError:
        return 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return 0

    ids: Set[str] = set()
    for line in out.splitlines():
        line = line.strip()
        if not line or "\t" not in line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        cid, image, names = parts[0], parts[1], parts[2]
        label = parts[3] if len(parts) > 3 else ""
        if not is_terminal_sandbox_container(image=image, names=names, session_label=label):
            continue
        ids.add(cid)

    removed = 0
    for cid in ids:
        if dry_run:
            removed += 1
            continue
        try:
            subprocess.run(
                ["docker", "rm", "-f", cid],
                capture_output=True,
                timeout=60,
                check=False,
            )
            removed += 1
        except (subprocess.TimeoutExpired, OSError):
            pass
    return removed
