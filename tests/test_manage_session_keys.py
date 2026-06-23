"""Tests for manage-session-keys.sh marker semantics (no root required)."""

from __future__ import annotations

import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "docker" / "pkg" / "manage-session-keys.sh"
MARKER_RE = re.compile(r"mcp-term-session=([0-9a-fA-F-]{36})")


def test_manage_session_keys_script_exists_and_executable() -> None:
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & 0o111


def test_marker_regex_matches_session_comment() -> None:
    line = (
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleKeyComment "
        "mcp-term-session=00000000-0000-4000-8000-000000000001 ttl=2026-01-01T00:00:00+00:00"
    )
    match = MARKER_RE.search(line)
    assert match is not None
    assert match.group(1) == "00000000-0000-4000-8000-000000000001"
