"""
Output file read operations for mcp_terminal (C-008).

Provides read, tail, search, and stat operations on per-command
stdout/stderr output files. Enforces path containment and
rejects invalid stream names.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from mcp_terminal.services.command_history import CommandHistory

VALID_STREAMS: frozenset = frozenset({"stdout", "stderr"})
DEFAULT_MAX_BYTES: int = 65536
DEFAULT_TAIL_LINES: int = 100
DEFAULT_MAX_MATCHES: int = 50


@dataclass(frozen=True)
class SearchMatch:
    """One regex match from output search."""

    seq: int
    stream: str
    line_number: int
    text: str  # full matched line


@dataclass(frozen=True)
class StatResult:
    """Output file sizes for terminal_stat (no file content)."""

    seq: int
    stdout_bytes: int
    stderr_bytes: int
    stdout_file: str
    stderr_file: str


class OutputReader:
    """Read operations on per-command output files (C-008).

    All operations validate stream name and resolve file paths from seq
    to prevent path traversal.
    """

    def __init__(self, session_dir: Path) -> None:
        self._session_dir = session_dir

    def _resolve_file(self, seq: int, stream: str) -> tuple[Optional[Path], Optional[str]]:
        """Resolve and validate the output file path for seq and stream.

        Returns:
            (Path, None) on success, or (None, error_code) on rejection.
        """
        if stream not in VALID_STREAMS:
            return None, "INVALID_STREAM"
        prefix = CommandHistory.seq_to_prefix(seq)
        path = self._session_dir / f"{prefix}.{stream}.log"
        # Path containment check
        try:
            path.resolve().relative_to(self._session_dir.resolve())
        except ValueError:
            return None, "INVALID_CWD"
        return path, None

    def read(
        self,
        seq: int,
        stream: str,
        *,
        offset: int = 0,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> tuple[Optional[bytes], Optional[str]]:
        """Read bytes from an output file starting at offset.

        Returns:
            (bytes, None) on success, or (None, error_code) on failure.
        """
        path, err = self._resolve_file(seq, stream)
        if err is not None:
            return None, err
        assert path is not None
        if not path.exists():
            return b"", None
        with path.open("rb") as fh:
            fh.seek(offset)
            return fh.read(max_bytes), None

    def tail(
        self,
        seq: int,
        stream: str,
        *,
        lines: int = DEFAULT_TAIL_LINES,
    ) -> tuple[Optional[List[str]], Optional[str]]:
        """Return the last N lines from an output file."""
        path, err = self._resolve_file(seq, stream)
        if err is not None:
            return None, err
        assert path is not None
        if not path.exists():
            return [], None
        content = path.read_text(encoding="utf-8", errors="replace")
        all_lines = content.splitlines()
        return all_lines[-lines:], None

    def search(
        self,
        seq: int,
        stream: str,
        pattern: str,
        *,
        max_matches: int = DEFAULT_MAX_MATCHES,
    ) -> tuple[Optional[List[SearchMatch]], Optional[str]]:
        """Search an output file for lines matching the regex pattern."""
        path, err = self._resolve_file(seq, stream)
        if err is not None:
            return None, err
        assert path is not None
        if not path.exists():
            return [], None
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return None, f"INVALID_PATTERN: {exc}"
        matches: List[SearchMatch] = []
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                matches.append(SearchMatch(seq=seq, stream=stream, line_number=line_no, text=line))
                if len(matches) >= max_matches:
                    break
        return matches, None

    def stat(self, seq: int) -> StatResult:
        """Return output file sizes for terminal_stat (no file content)."""
        prefix = CommandHistory.seq_to_prefix(seq)
        stdout_file = f"{prefix}.stdout.log"
        stderr_file = f"{prefix}.stderr.log"
        stdout_path = self._session_dir / stdout_file
        stderr_path = self._session_dir / stderr_file
        return StatResult(
            seq=seq,
            stdout_bytes=stdout_path.stat().st_size if stdout_path.exists() else 0,
            stderr_bytes=stderr_path.stat().st_size if stderr_path.exists() else 0,
            stdout_file=stdout_file,
            stderr_file=stderr_file,
        )
