"""
Command history and sequence management for mcp_terminal (C-006, C-007).

Manages the per-session history.jsonl file and allocates monotonically
increasing seq numbers for output file naming.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class CommandRecord:
    """Single history.jsonl entry for one executed command (C-006)."""

    seq: int
    job_id: Optional[str]
    project_id: str
    session_id: str
    timestamp: str
    execution_kind: str
    command: Optional[str]
    argv: Optional[List[str]]
    resolved_argv: List[str]
    cwd: str
    mode: str
    network: str
    image_profile: str
    status: str = "pending"
    exit_code: Optional[int] = None
    timed_out: Optional[bool] = None
    stdout_file: str = ""
    stderr_file: str = ""
    meta_file: str = ""


class CommandHistory:
    """Manages the append-only history.jsonl for a terminal session (C-006/C-007)."""

    def __init__(self, session_dir: Path) -> None:
        self._session_dir = session_dir
        self._history_file = session_dir / "history.jsonl"
        self._logger = logging.getLogger(__name__)

    def allocate_seq(self) -> int:
        """Allocate the next session-local command sequence number.

        Reads the current maximum seq from history.jsonl (0 if empty),
        increments by 1. The result is the stable external reference for
        the new command within this session.

        Returns:
            Next seq as a positive integer (1-based).
        """
        if not self._history_file.exists():
            return 1
        max_seq = 0
        try:
            for line in self._history_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                max_seq = max(max_seq, entry.get("seq", 0))
        except Exception:  # noqa: BLE001
            pass
        return max_seq + 1

    @staticmethod
    def seq_to_prefix(seq: int) -> str:
        """Return zero-padded 6-digit prefix for seq."""
        return f"{seq:06d}"

    def pre_create_output_files(self, seq: int) -> tuple[str, str, str]:
        """Create empty output files for the given seq before the job starts.

        Args:
            seq: Allocated command sequence number.

        Returns:
            Tuple of (stdout_file, stderr_file, meta_file) relative file names.
        """
        prefix = self.seq_to_prefix(seq)
        stdout_file = f"{prefix}.stdout.log"
        stderr_file = f"{prefix}.stderr.log"
        meta_file = f"{prefix}.meta.json"
        for fname in (stdout_file, stderr_file):
            (self._session_dir / fname).touch()
        (self._session_dir / meta_file).write_text(
            json.dumps({"seq": seq, "status": "pending"}),
            encoding="utf-8",
        )
        return stdout_file, stderr_file, meta_file

    def append_record(self, record: CommandRecord) -> None:
        """Append a CommandRecord as a JSON line to history.jsonl."""
        line = json.dumps(asdict(record), ensure_ascii=False)
        with self._history_file.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def update_record(
        self,
        seq: int,
        *,
        status: str,
        exit_code: Optional[int] = None,
        timed_out: Optional[bool] = None,
        job_id: Optional[str] = None,
    ) -> None:
        """Rewrite the history.jsonl entry for seq with updated fields.

        Reads all lines, finds the entry with matching seq, updates it,
        and rewrites the full file. Intended for post-execution updates only.
        """
        if not self._history_file.exists():
            return
        lines = []
        for line in self._history_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("seq") == seq:
                entry["status"] = status
                if exit_code is not None:
                    entry["exit_code"] = exit_code
                if timed_out is not None:
                    entry["timed_out"] = timed_out
                if job_id is not None:
                    entry["job_id"] = job_id
            lines.append(json.dumps(entry, ensure_ascii=False))
        self._history_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def list_records(
        self,
        *,
        limit: int = 25,
        offset: int = 0,
    ) -> List[CommandRecord]:
        """Return up to limit CommandRecords in descending timestamp order."""
        if not self._history_file.exists():
            return []
        records = []
        for line in self._history_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            records.append(CommandRecord(**json.loads(line)))
        records.sort(key=lambda r: r.timestamp, reverse=True)
        return records[offset : offset + limit]
