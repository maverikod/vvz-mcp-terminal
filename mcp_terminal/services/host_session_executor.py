"""
Host-side terminal command execution (no Docker session container).

Used when ``terminal.host_execution`` is enabled and the command is on the allowlist.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import shlex
import subprocess
import textwrap
from pathlib import Path
from typing import List, Optional

from mcp_terminal.services.command_history import CommandHistory
from mcp_terminal.services.shell_state import (
    ShellState,
    normalize_cwd,
    read_shell_state,
    write_shell_state,
)
from mcp_terminal.services.host_execution_config import (
    get_host_execution_config,
    validate_host_run_request,
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


def _write_host_exec_script(
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
    """Write a bash script under the session dir for one host-side execution."""
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
    path = session_dir / f"{prefix}.host.exec.sh"
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


class HostSessionExecutor:
    """Run one command directly on the host under the project workspace."""

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

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
    ) -> tuple[Optional[int], bool, str]:
        """Return ``(exit_code, timed_out, status)``."""
        if not get_host_execution_config().enabled:
            self._logger.error("host exec rejected seq=%d: host_execution disabled", seq)
            return None, False, "failed"

        validation = validate_host_run_request(execution_kind, command, argv)
        if not validation.ok:
            self._logger.error(
                "host exec rejected seq=%d: %s %s",
                seq,
                validation.error_code,
                validation.detail,
            )
            return None, False, "failed"

        prefix = CommandHistory.seq_to_prefix(seq)
        script_path = _write_host_exec_script(
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
        exit_code: Optional[int] = None
        timed_out = False
        status = "failed"
        proc: Optional[subprocess.Popen] = None

        try:
            with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
                proc = subprocess.Popen(  # noqa: S603
                    ["/bin/bash", str(script_path)],
                    stdout=out,
                    stderr=err,
                    cwd=str(project_dir.resolve()),
                )
                from mcp_terminal.services.running_terminal_jobs import (  # noqa: PLC0415
                    register,
                    unregister,
                )

                register(session_id, seq, proc)
                try:
                    proc.wait(timeout=timeout_seconds)
                    exit_code = proc.returncode
                    status = "completed"
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    timed_out = True
                    status = "completed"
                finally:
                    unregister(session_id, seq)
        except Exception as exc:  # noqa: BLE001
            self._logger.error("host exec failed seq=%d: %s", seq, exc)
            status = "failed"

        new_state = read_shell_state(session_dir)
        write_shell_state(
            session_dir,
            ShellState(cwd=new_state.cwd, use_venv=new_state.use_venv),
        )

        try:
            script_path.unlink(missing_ok=True)
        except OSError:
            pass

        return exit_code, timed_out, status
