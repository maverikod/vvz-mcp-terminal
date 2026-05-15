"""Tests for running terminal job registry and kill."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

from mcp_terminal.services import running_terminal_jobs as rtj


def test_register_kill_unregister() -> None:
    proc = MagicMock(spec=subprocess.Popen)
    rtj.register("sid-1", 3, proc)
    assert rtj.kill("sid-1", 3) is True
    proc.kill.assert_called_once()
    rtj.unregister("sid-1", 3)
    assert rtj.kill("sid-1", 3) is False


def test_kill_missing_returns_false() -> None:
    assert rtj.kill("no-such", 99) is False
