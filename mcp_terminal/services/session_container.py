"""
Session-scoped Docker container lifecycle: start → load state → exec → save state → stop.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import logging
import shlex
import subprocess
import textwrap
from pathlib import Path
from typing import List, Optional

from mcp_terminal.services.command_history import CommandHistory
from mcp_terminal.services.container_runner import ContainerRunner, ContainerSpec
from mcp_terminal.services.docker_hosts import (
    docker_run_add_host_args,
    parse_docker_host_mappings,
    resolve_container_network_mode,
)
from mcp_terminal.services.pid_namespace import apply_docker_pid_namespace
from mcp_terminal.services.shell_state import (
    ShellState,
    normalize_cwd,
    read_shell_state,
    write_shell_state,
)
from mcp_terminal.services.venv_activation import venv_activation_shell_block

_SESSION_LABEL = "mcp.terminal.session=true"
_IDLE_CMD = ["sleep", "infinity"]
_SAVE_CWD_PY = textwrap.dedent(
    """\
    import json, os
    from pathlib import Path
    ws = Path("/workspace").resolve()
    try:
        cur = Path(os.getcwd()).resolve()
        if cur == ws:
            rel = "."
        elif ws in cur.parents:
            rel = str(cur.relative_to(ws))
        else:
            rel = "."
    except Exception:
        rel = "."
    p = Path("/session-state/shell_state.json")
    data = {}
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["version"] = 1
    data["cwd"] = rel
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    """
)


def session_container_name(project_id: str, session_id: str) -> str:
    """Stable Docker container name for ``(project_id, session_id)``."""
    digest = hashlib.sha256(f"{project_id}\0{session_id}".encode()).hexdigest()[:16]
    return f"mcp-term-{digest}"


def spec_fingerprint(spec: ContainerSpec) -> str:
    """Hash mount/write settings that require container recreation when changed."""
    m = spec.mount_spec
    raw = (
        f"{spec.image}|{m.workspace_readonly}|{spec.user}|"
        f"{spec.network_spec}|{spec.pid_namespace}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _docker_inspect_running(name: str) -> bool:
    try:
        out = subprocess.check_output(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        return out.strip().lower() == "true"
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _docker_container_id(name: str) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["docker", "inspect", "-f", "{{.Id}}", name],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        cid = out.strip()
        return cid or None
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def stop_session_container(project_id: str, session_id: str) -> bool:
    """Force-remove the session container if it exists. Returns True unless docker is missing."""
    name = session_container_name(project_id, session_id)
    try:
        subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True,
            timeout=60,
            check=False,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _build_start_cmd(
    runner: ContainerRunner,
    *,
    name: str,
    spec: ContainerSpec,
    session_dir: Path,
) -> List[str]:
    """``docker run -d`` for a long-idle session container (no ``--rm``)."""
    m = spec.mount_spec
    ro = ":ro" if m.workspace_readonly else ":rw"
    ws = m.workspace_source
    host_mappings = parse_docker_host_mappings()
    cmd: List[str] = [
        runner._runtime,  # noqa: SLF001
        "run",
        "-d",
        "--name",
        name,
        "--label",
        _SESSION_LABEL,
        "--user",
        spec.user,
        "--workdir",
        "/workspace",
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
        resolve_container_network_mode(spec.network_spec),
        "-v",
        f"{ws}:/workspace{ro}",
        "-v",
        f"{session_dir.resolve()}:/session-state:rw",
    ]
    apply_docker_pid_namespace(cmd, spec.pid_namespace)
    cmd.extend(docker_run_add_host_args(host_mappings))
    for key, val in spec.environment.items():
        cmd += ["-e", f"{key}={val}"]
    cmd.append(spec.image)
    cmd.extend(_IDLE_CMD)
    return cmd


def _write_exec_script(
    session_dir: Path,
    prefix: str,
    *,
    effective_cwd: str,
    execution_kind: str,
    command: Optional[str],
    argv: Optional[List[str]],
    use_venv: bool = True,
) -> Path:
    """Write a host-side script mounted into the container for one execution."""
    cwd = normalize_cwd(effective_cwd)
    if execution_kind == "shell":
        # Run in the exec script's shell (not bash -lc) so cd persists for state save.
        user_body = command.strip() if command and command.strip() else "true"
    else:
        parts = [shlex.quote(str(x)) for x in (argv or [])]
        if not parts:
            user_body = "false"
        else:
            user_body = " ".join(parts)
    py_load = (
        "import json,sys;d=json.load(open(sys.argv[1]));"
        'print(d.get("cwd",".") or ".")'
    )
    load_cwd = (
        f"CWD=$(python3 -c {shlex.quote(py_load)} \"$STATE\" 2>/dev/null)"
        f" || CWD={shlex.quote(cwd)}"
    )
    venv_block = venv_activation_shell_block(use_venv=use_venv)
    script = textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        STATE=/session-state/shell_state.json
        CWD={shlex.quote(cwd)}
        if [ -f "$STATE" ]; then
          {load_cwd}
        fi
        if [ "$CWD" = "." ]; then
          cd /workspace
        else
          cd "/workspace/$CWD" || cd /workspace
        fi
        {venv_block}{user_body}
        ec=$?
        python3 <<'PYEND'
{_SAVE_CWD_PY}
PYEND
        exit $ec
        """
    )
    path = session_dir / f"{prefix}.exec.sh"
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


def _build_exec_cmd(
    runner: ContainerRunner,
    *,
    container_name: str,
    spec: ContainerSpec,
    script_name: str,
) -> List[str]:
    return [
        runner._runtime,  # noqa: SLF001
        "exec",
        "-u",
        spec.user,
        container_name,
        "bash",
        f"/session-state/{script_name}",
    ]


class SessionContainerExecutor:
    """Run the start → exec → state → stop (optional) cycle for one command seq."""

    def __init__(self, runner: Optional[ContainerRunner] = None) -> None:
        self._runner = runner or ContainerRunner()
        self._logger = logging.getLogger(__name__)

    def run(
        self,
        *,
        project_id: str,
        session_id: str,
        seq: int,
        session_dir: Path,
        spec: ContainerSpec,
        timeout_seconds: int,
        keep_container: bool,
        effective_cwd: str,
        execution_kind: str,
        command: Optional[str],
        argv: Optional[List[str]],
        use_venv: bool = True,
    ) -> tuple[Optional[int], bool, str]:
        """Return ``(exit_code, timed_out, status)``."""
        name = session_container_name(project_id, session_id)
        fp = spec_fingerprint(spec)
        prefix = CommandHistory.seq_to_prefix(seq)
        script_path = _write_exec_script(
            session_dir,
            prefix,
            effective_cwd=effective_cwd,
            execution_kind=execution_kind,
            command=command,
            argv=argv,
            use_venv=use_venv,
        )
        script_name = script_path.name

        state = read_shell_state(session_dir)
        need_start = True
        if _docker_inspect_running(name):
            if state.spec_fingerprint == fp:
                need_start = False
            else:
                self._logger.info("Recreating session container %s (spec changed)", name)
                stop_session_container(project_id, session_id)

        if need_start:
            stop_session_container(project_id, session_id)
            start_cmd = _build_start_cmd(
                self._runner, name=name, spec=spec, session_dir=session_dir
            )
            try:
                subprocess.run(
                    start_cmd,
                    capture_output=True,
                    timeout=120,
                    check=True,
                )
            except (
                subprocess.CalledProcessError,
                FileNotFoundError,
                subprocess.TimeoutExpired,
            ) as exc:
                self._logger.error("Session container start failed: %s", exc)
                return None, False, "failed"

        if not _docker_inspect_running(name):
            return None, False, "failed"

        cid = _docker_container_id(name)
        exec_cmd = _build_exec_cmd(
            self._runner,
            container_name=name,
            spec=spec,
            script_name=script_name,
        )
        exit_code: Optional[int] = None
        timed_out = False
        status = "failed"
        proc: Optional[subprocess.Popen] = None
        stdout_path = session_dir / f"{prefix}.stdout.log"
        stderr_path = session_dir / f"{prefix}.stderr.log"

        try:
            with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
                proc = subprocess.Popen(  # noqa: S603
                    exec_cmd,
                    stdout=out,
                    stderr=err,
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
            self._logger.error("docker exec failed seq=%d: %s", seq, exc)
            status = "failed"

        new_state = read_shell_state(session_dir)
        if keep_container and _docker_inspect_running(name):
            write_shell_state(
                session_dir,
                ShellState(
                    cwd=new_state.cwd,
                    container_id=cid,
                    container_name=name,
                    spec_fingerprint=fp,
                    use_venv=new_state.use_venv,
                ),
            )
        else:
            stop_session_container(project_id, session_id)
            write_shell_state(
                session_dir,
                ShellState(cwd=new_state.cwd, use_venv=new_state.use_venv),
            )

        try:
            script_path.unlink(missing_ok=True)
        except OSError:
            pass

        return exit_code, timed_out, status
