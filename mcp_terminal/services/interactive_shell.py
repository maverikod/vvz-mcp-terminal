"""In-memory PTY sessions attached to kept sandbox containers."""

from __future__ import annotations

import errno
import os
import pty
import select
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from mcp_terminal.services.session_container import (
    _docker_inspect_running,
    session_container_name,
)


@dataclass
class InteractiveShell:
    project_id: str
    session_id: str
    shell_id: str
    container_name: str
    master_fd: int
    proc: subprocess.Popen[bytes]
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    offset: int = 0
    buffer: bytearray = field(default_factory=bytearray)


_SHELLS: Dict[str, InteractiveShell] = {}
_LOCK = threading.RLock()
_MAX_BUFFER = 1024 * 1024


def _make_shell_id(project_id: str, session_id: str) -> str:
    return f"{project_id}:{session_id}"


def _drain_locked(shell: InteractiveShell) -> None:
    while True:
        rlist, _, _ = select.select([shell.master_fd], [], [], 0)
        if not rlist:
            break
        try:
            chunk = os.read(shell.master_fd, 65536)
        except OSError as exc:
            if exc.errno in (errno.EIO, errno.EBADF):
                break
            raise
        if not chunk:
            break
        shell.buffer.extend(chunk)
        if len(shell.buffer) > _MAX_BUFFER:
            drop = len(shell.buffer) - _MAX_BUFFER
            del shell.buffer[:drop]
            shell.offset += drop
    shell.updated_at = time.time()


def attach_shell(
    *,
    project_id: str,
    session_id: str,
    user: Optional[str] = None,
    cwd: str = "/workspace",
    command: str = "bash",
    cols: int = 120,
    rows: int = 30,
    runtime: str = "docker",
) -> tuple[Optional[InteractiveShell], Optional[str]]:
    """Start or return a PTY shell in an existing kept sandbox container."""
    shell_id = _make_shell_id(project_id, session_id)
    container_name = session_container_name(project_id, session_id)
    with _LOCK:
        existing = _SHELLS.get(shell_id)
        if existing is not None and existing.proc.poll() is None:
            _drain_locked(existing)
            return existing, None
        if existing is not None:
            close_shell(shell_id=shell_id)
        if not _docker_inspect_running(container_name):
            return None, "CONTAINER_NOT_RUNNING"
        master_fd, slave_fd = pty.openpty()
        exec_cmd = [
            runtime,
            "exec",
            "-i",
            "-t",
            "-w",
            cwd,
            container_name,
            command,
        ]
        if user:
            exec_cmd[4:4] = ["-u", user]
        proc = subprocess.Popen(  # noqa: S603
            exec_cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )
        os.close(slave_fd)
        os.set_blocking(master_fd, False)
        shell = InteractiveShell(
            project_id=project_id,
            session_id=session_id,
            shell_id=shell_id,
            container_name=container_name,
            master_fd=master_fd,
            proc=proc,
        )
        _SHELLS[shell_id] = shell
        resize_shell(shell_id=shell_id, cols=cols, rows=rows)
        return shell, None


def shell_status(shell: InteractiveShell) -> dict:
    return {
        "shell_id": shell.shell_id,
        "project_id": shell.project_id,
        "session_id": shell.session_id,
        "container_name": shell.container_name,
        "running": shell.proc.poll() is None,
        "exit_code": shell.proc.poll(),
        "offset": shell.offset + len(shell.buffer),
    }


def send_shell(*, shell_id: str, data: str) -> Optional[str]:
    with _LOCK:
        shell = _SHELLS.get(shell_id)
        if shell is None:
            return "NOT_FOUND"
        if shell.proc.poll() is not None:
            _drain_locked(shell)
            return "SHELL_EXITED"
        os.write(shell.master_fd, data.encode("utf-8"))
        shell.updated_at = time.time()
        return None


def read_shell(
    *, shell_id: str, offset: Optional[int], max_bytes: int
) -> tuple[Optional[dict], Optional[str]]:
    with _LOCK:
        shell = _SHELLS.get(shell_id)
        if shell is None:
            return None, "NOT_FOUND"
        _drain_locked(shell)
        start = shell.offset if offset is None else max(offset, shell.offset)
        rel = start - shell.offset
        payload = bytes(shell.buffer[rel : rel + max_bytes])
        next_offset = start + len(payload)
        return (
            {
                **shell_status(shell),
                "data": payload.decode("utf-8", errors="replace"),
                "next_offset": next_offset,
                "truncated_before_offset": shell.offset,
            },
            None,
        )


def resize_shell(*, shell_id: str, cols: int, rows: int) -> Optional[str]:
    with _LOCK:
        shell = _SHELLS.get(shell_id)
        if shell is None:
            return "NOT_FOUND"
        try:
            import fcntl
            import struct
            import termios

            packed = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(shell.master_fd, termios.TIOCSWINSZ, packed)
            if shell.proc.poll() is None:
                shell.proc.send_signal(signal.SIGWINCH)
        except OSError:
            return "RESIZE_FAILED"
        shell.updated_at = time.time()
        return None


def close_shell(*, shell_id: str) -> Optional[str]:
    with _LOCK:
        shell = _SHELLS.pop(shell_id, None)
        if shell is None:
            return "NOT_FOUND"
        try:
            if shell.proc.poll() is None:
                shell.proc.terminate()
                try:
                    shell.proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    shell.proc.kill()
                    shell.proc.wait(timeout=3)
        finally:
            try:
                os.close(shell.master_fd)
            except OSError:
                pass
        return None
