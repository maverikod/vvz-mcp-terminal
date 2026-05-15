"""
TerminalExecutionJob: queue job for sandbox container execution (C-009).

Executes commands inside isolated containers and writes stdout/stderr
exclusively to per-command output files. Never runs synchronously.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from mcp_terminal.services.command_history import CommandHistory
from mcp_terminal.services.container_runner import ContainerRunner, ContainerSpec
from mcp_terminal.services.running_terminal_jobs import register, unregister


@dataclass(frozen=True)
class JobParams:
    """Immutable parameters for one TerminalExecutionJob invocation."""

    project_id: str
    session_id: str
    seq: int
    session_dir: Path
    container_spec: ContainerSpec
    timeout_seconds: int


class TerminalExecutionJob:
    """Queue job that performs sandbox container execution (C-009).

    The run() method is called by the adapter queue worker in a background
    thread. It must never be called directly from request handlers.
    QueueResultSemantics (C-011): a completed job does not imply the
    terminal command succeeded; callers must check exit_code and timed_out.
    """

    def __init__(self, params: JobParams, runner: Optional[ContainerRunner] = None) -> None:
        """Initialise the job with parameters and optional runner override.

        Args:
            params: Immutable job parameters including session_dir and container_spec.
            runner: Optional ContainerRunner override for testing; defaults to
                ContainerRunner() with the 'docker' runtime.
        """
        self._params = params
        self._runner = runner or ContainerRunner()
        self._logger = logging.getLogger(__name__)

    def run(self) -> dict:
        """Execute the container job and write output files.

        Starts the container, redirects stdout to NNNNNN.stdout.log and stderr
        to NNNNNN.stderr.log, waits for completion or timeout, then updates
        NNNNNN.meta.json and history.jsonl. Stops and removes the container
        regardless of outcome (cleanup_always=True, C-009 invariant).

        QueueResultSemantics (C-011): status='completed' means the worker
        ran the full lifecycle. Terminal success additionally requires
        exit_code==0 and timed_out==False.

        Returns:
            dict with keys: exit_code (int or None), timed_out (bool),
            status (str: 'completed' | 'failed').
        """
        p = self._params
        prefix = CommandHistory.seq_to_prefix(p.seq)
        stdout_path = p.session_dir / f"{prefix}.stdout.log"
        stderr_path = p.session_dir / f"{prefix}.stderr.log"
        meta_path = p.session_dir / f"{prefix}.meta.json"

        cmd = self._runner.build_cmd(p.container_spec)
        self._logger.info("Starting container for seq=%d cmd[0]=%s", p.seq, cmd[0])

        exit_code: Optional[int] = None
        timed_out = False
        status = "failed"
        proc: Optional[subprocess.Popen] = None

        try:
            with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
                proc = subprocess.Popen(  # noqa: S603
                    cmd,
                    stdout=out,
                    stderr=err,
                )
                register(p.session_id, p.seq, proc)
                try:
                    proc.wait(timeout=p.timeout_seconds)
                    exit_code = proc.returncode
                    status = "completed"
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    timed_out = True
                    exit_code = None
                    status = "completed"  # lifecycle complete; command timed out
        except Exception as exc:  # noqa: BLE001
            self._logger.error("Container run failed for seq=%d: %s", p.seq, exc)
            status = "failed"
        finally:
            if proc is not None:
                unregister(p.session_id, p.seq)

        # Update meta.json
        meta = {"seq": p.seq, "status": status, "exit_code": exit_code, "timed_out": timed_out}
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        # Update history.jsonl entry
        history = CommandHistory(p.session_dir)
        history.update_record(p.seq, status=status, exit_code=exit_code, timed_out=timed_out)

        self._logger.info(
            "Job complete seq=%d status=%s exit_code=%s timed_out=%s",
            p.seq,
            status,
            exit_code,
            timed_out,
        )
        return {"exit_code": exit_code, "timed_out": timed_out, "status": status}
