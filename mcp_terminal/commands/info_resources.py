"""Packaged resources for the MCP Terminal ``info`` command."""

from __future__ import annotations

from importlib.resources import files
from typing import Any

from mcp_terminal.package_info import DEBIAN_PACKAGE_NAME, PACKAGE_NAME, package_version

TERMINAL_INFO_GUIDE_VERSION = "1.0"
TERMINAL_INFO_SUMMARY = (
    "CA session_create -> terminal_session_create -> terminal_run -> status/read -> cleanup"
)


def load_terminal_info_markdown() -> str:
    """Read the packaged MCP Terminal guide."""
    return files("mcp_terminal").joinpath("docs").joinpath("INFO.md").read_text(encoding="utf-8")


TERMINAL_INFO_MARKDOWN = load_terminal_info_markdown()

TERMINAL_INFO_LIFECYCLE = [
    "Create a Code Analysis Server session with session_create.",
    "Create or reopen terminal state with terminal_session_create.",
    "Run sandbox commands with terminal_run and poll terminal_get_status.",
    "Read command output with terminal_read or terminal_tail.",
    "Attach an interactive PTY only to a kept sandbox container when needed.",
    "Use terminal_host_exec only for allowlisted real-host commands.",
    "Clean up with terminal_detach, terminal_delete, and session_delete.",
]

TERMINAL_INFO_DOCS = [
    "man mcp-terminal-docker",
    "man mcp-terminal-info",
    "man mcp-terminal-preflight",
    "man mcp-terminal-config",
    "info mcp-terminal-docker",
    "/usr/share/doc/mcp-terminal-docker/MCP_TERMINAL_INFO.md",
]


def terminal_package_info() -> dict[str, str]:
    version = package_version()
    return {
        "project_name": PACKAGE_NAME,
        "debian_package": DEBIAN_PACKAGE_NAME,
        "version": version,
        "service_image_tag": version,
    }


def registered_command_entries() -> list[dict[str, Any]]:
    """Return the live command catalog from the canonical registration list."""
    from mcp_terminal.term_server import _TERMINAL_COMMAND_TYPES

    return [
        {
            "name": str(cmd_cls.name),
            "version": str(getattr(cmd_cls, "version", "")),
            "description": str(getattr(cmd_cls, "descr", "")).strip(),
            "category": str(getattr(cmd_cls, "category", "")),
        }
        for cmd_cls in _TERMINAL_COMMAND_TYPES
    ]
