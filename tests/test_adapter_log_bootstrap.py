"""Tests for adapter log bootstrap (packaged container layout)."""

from __future__ import annotations

from pathlib import Path

from mcp_terminal.adapter_log_bootstrap import ensure_adapter_log_dir


def test_ensure_adapter_log_dir_creates_target(tmp_path: Path, monkeypatch) -> None:
    log_root = tmp_path / "var" / "log" / "mcp-terminal"
    monkeypatch.setenv("MCP_TERMINAL_CONFIG_DIR", str(tmp_path / "etc" / "mcp-terminal"))
    monkeypatch.setenv("MCP_TERMINAL_LOG_DIR", str(log_root))
    ensure_adapter_log_dir()
    assert log_root.is_dir()
