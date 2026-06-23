"""
Real host command execution via SSH (not in-container subprocess).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import shlex
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from mcp_terminal.errors import ErrorCode
from mcp_terminal.services.command_history import CommandHistory
from mcp_terminal.services.host_execution_config import (
    get_host_execution_config,
    validate_host_run_request,
)
from mcp_terminal.services.session_ssh_key import session_key_paths
from mcp_terminal.services.shell_state import (
    ShellState,
    normalize_cwd,
    read_shell_state,
    write_shell_state,
)
from mcp_terminal.services.venv_activation import host_venv_activation_shell_block

_SAVE_CWD_PY = textwrap.dedent(
    """\
    import json, os, sys
    from pathlib import Path
    project = Path(sys.argv[1]).resolve()
    state_path = Path(sys.argv[2])
    try:
        cur = Path(os.getcwd()).resolve()
        if cur == project:
            rel = "."
        elif project in cur.parents:
            rel = str(cur.relative_to(project))
        else:
            rel = "."
    except Exception:
        rel = "."
    data = {}
    if state_path.is_file():
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["version"] = 1
    data["cwd"] = rel
    state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    """
)


@dataclass(frozen=True)
class HostSSHRunResult:
    """Outcome of one SSH host-side execution."""

    exit_code: Optional[int]
    timed_out: bool
    status: str
    target_user: Optional[str] = None
    error_code: Optional[str] = None


def _write_remote_exec_script(
    session_dir: Path,
    prefix: str,
    *,
    project_dir: Path,
    effective_cwd: str,
    execution_kind: str,
    command: Optional[str],
    argv: Optional[List[str]],
    use_venv: bool = True,
) -> Path:
    """Write a bash script locally; contents are sent to the remote host via SSH."""
    cwd = normalize_cwd(effective_cwd)
    project = project_dir.resolve()
    if execution_kind == "shell":
        user_body = command.strip() if command and command.strip() else "true"
    else:
        parts = [shlex.quote(str(x)) for x in (argv or [])]
        user_body = " ".join(parts) if parts else "false"

    py_load = (
        "import json,sys;d=json.load(open(sys.argv[1]));"
        'print(d.get("cwd",".") or ".")'
    )
    state_file = session_dir / "shell_state.json"
    load_cwd = (
        f"CWD=$(python3 -c {shlex.quote(py_load)} {shlex.quote(str(state_file))} 2>/dev/null)"
        f" || CWD={shlex.quote(cwd)}"
    )
    venv_block = host_venv_activation_shell_block(project, use_venv=use_venv)
    script = textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        PROJECT={shlex.quote(str(project))}
        CWD={shlex.quote(cwd)}
        if [ -f {shlex.quote(str(state_file))} ]; then
          {load_cwd}
        fi
        if [ "$CWD" = "." ]; then
          cd "$PROJECT"
        else
          cd "$PROJECT/$CWD" || cd "$PROJECT"
        fi
        {venv_block}{user_body}
        ec=$?
        python3 -c {shlex.quote(_SAVE_CWD_PY)} "$PROJECT" {shlex.quote(str(state_file))}
        exit $ec
        """
    )
    path = session_dir / f"{prefix}.host_ssh.exec.sh"
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


def _classify_ssh_failure(stderr_text: str) -> Optional[str]:
    lower = stderr_text.lower()
    if "host key verification failed" in lower or "no matching host key" in lower:
        return ErrorCode.HOST_HOST_KEY_MISMATCH
    if (
        "connection refused" in lower
        or "connection timed out" in lower
        or "no route to host" in lower
        or "network is unreachable" in lower
        or "could not resolve hostname" in lower
    ):
        return ErrorCode.HOST_SSH_UNREACHABLE
    return None


class HostSSHExecutor:
    """Run one allowlisted command on the real host via SSH."""

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        self._last_target_user: Optional[str] = None

    @property
    def last_target_user(self) -> Optional[str]:
        return self._last_target_user

    def run(
        self,
        *,
        project_id: str,
        session_id: str,
        seq: int,
        session_dir: Path,
        project_dir: Path,
        timeout_seconds: int,
        effective_cwd: str,
        execution_kind: str,
        command: Optional[str],
        argv: Optional[List[str]],
        use_venv: bool = True,
        target_user: Optional[str] = None,
    ) -> HostSSHRunResult:
        """Execute on the real host via SSH."""
        self._last_target_user = None
        he = get_host_execution_config()
        if not he.enabled or he.ssh is None or not he.ssh_ready():
            return HostSSHRunResult(
                None,
                False,
                "failed",
                error_code=ErrorCode.HOST_EXECUTION_DISABLED,
            )

        validation = validate_host_run_request(
            execution_kind,
            command,
            argv,
            session_dir=session_dir,
            target_user=target_user,
        )
        if not validation.ok:
            return HostSSHRunResult(
                None,
                False,
                "failed",
                error_code=validation.error_code or ErrorCode.HOST_COMMAND_NOT_ALLOWED,
            )

        from mcp_terminal.services.host_execution_config import resolve_target_user

        resolved_user, tu_err = resolve_target_user(target_user, config=he)
        if tu_err is not None or resolved_user is None:
            return HostSSHRunResult(
                None,
                False,
                "failed",
                error_code=tu_err or ErrorCode.TARGET_USER_NOT_ALLOWED,
            )
        self._last_target_user = resolved_user

        private_key, _pub = session_key_paths(session_dir)
        if not private_key.is_file():
            return HostSSHRunResult(
                None,
                False,
                "failed",
                error_code=ErrorCode.HOST_EXECUTION_DISABLED,
            )

        prefix = CommandHistory.seq_to_prefix(seq)
        script_path = _write_remote_exec_script(
            session_dir,
            prefix,
            project_dir=project_dir,
            effective_cwd=effective_cwd,
            execution_kind=execution_kind,
            command=command,
            argv=argv,
            use_venv=use_venv,
        )
        stdout_path = session_dir / f"{prefix}.stdout.log"
        stderr_path = session_dir / f"{prefix}.stderr.log"

        remote_script = script_path.read_text(encoding="utf-8")
        ssh_argv = [
            "ssh",
            "-i",
            str(private_key),
            "-p",
            str(he.ssh.port),
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={he.ssh.known_hosts_path}",
            "-o",
            f"ConnectTimeout={he.ssh.connect_timeout}",
            "-o",
            "BatchMode=yes",
            f"{resolved_user}@{he.ssh.host}",
            "bash",
            "-s",
        ]

        exit_code: Optional[int] = None
        timed_out = False
        status = "failed"
        error_code: Optional[str] = None
        proc: Optional[subprocess.Popen] = None

        try:
            with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
                proc = subprocess.Popen(  # noqa: S603
                    ssh_argv,
                    stdin=subprocess.PIPE,
                    stdout=out,
                    stderr=err,
                )
                from mcp_terminal.services.running_terminal_jobs import (  # noqa: PLC0415
                    register,
                    unregister,
                )

                register(session_id, seq, proc)
                try:
                    assert proc.stdin is not None
                    proc.stdin.write(remote_script.encode("utf-8"))
                    proc.stdin.close()
                    proc.wait(timeout=timeout_seconds)
                    exit_code = proc.returncode
                    status = "completed"
                    if exit_code == 255 and stderr_path.is_file():
                        stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
                        error_code = _classify_ssh_failure(stderr_text)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    timed_out = True
                    status = "completed"
                finally:
                    unregister(session_id, seq)
        except Exception as exc:  # noqa: BLE001
            self._logger.error("host ssh exec failed seq=%d: %s", seq, exc)
            status = "failed"
            error_code = ErrorCode.HOST_SSH_UNREACHABLE

        new_state = read_shell_state(session_dir)
        write_shell_state(
            session_dir,
            ShellState(cwd=new_state.cwd, use_venv=new_state.use_venv),
        )

        try:
            script_path.unlink(missing_ok=True)
        except OSError:
            pass

        return HostSSHRunResult(
            exit_code,
            timed_out,
            status,
            target_user=resolved_user,
            error_code=error_code,
        )
