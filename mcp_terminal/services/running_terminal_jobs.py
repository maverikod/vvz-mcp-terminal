"""Track in-flight ``docker run`` subprocess handles for ``terminal_kill`` (SIGKILL).

Each ``TerminalExecutionJob`` registers its ``Popen`` between start and completion;
``terminal_kill`` resolves (session_id, seq) and calls ``Popen.kill()`` (SIGKILL on POSIX).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import subprocess
import threading
from typing import Dict, Tuple

_lock = threading.Lock()
_running: Dict[Tuple[str, int], subprocess.Popen] = {}


def register(session_id: str, seq: int, proc: subprocess.Popen) -> None:
    """Register ``proc`` while the container subprocess is active."""
    with _lock:
        _running[(session_id, seq)] = proc


def unregister(session_id: str, seq: int) -> None:
    """Remove registration (call in ``finally`` after wait/kill)."""
    with _lock:
        _running.pop((session_id, seq), None)


def kill(session_id: str, seq: int) -> bool:
    """Send SIGKILL to the ``docker``/``podman`` client child (POSIX ``Popen.kill``).

    Returns:
        True if a process was found and ``kill()`` was invoked.
    """
    with _lock:
        proc = _running.get((session_id, seq))
    if proc is None:
        return False
    try:
        proc.kill()
        return True
    except OSError:
        return False
