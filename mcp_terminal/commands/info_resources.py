"""Packaged resources for the MCP Terminal ``info`` command."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import math
from typing import Any

from mcp_terminal.package_info import DEBIAN_PACKAGE_NAME, PACKAGE_NAME, package_version

TERMINAL_INFO_GUIDE_VERSION = "1.2"
TERMINAL_INFO_SUMMARY = (
    "CA session_create -> terminal_session_create -> terminal_run -> status/read -> cleanup"
)
DEFAULT_INFO_PAGE_SIZE = 4
MAX_INFO_PAGE_SIZE = 12


@dataclass(frozen=True)
class InfoSection:
    """One top-level section from the packaged guide."""

    title: str
    markdown: str


@dataclass(frozen=True)
class InfoPage:
    """Paginated slice of the packaged guide."""

    page: int
    page_size: int
    total_sections: int
    total_pages: int
    has_prev: bool
    has_next: bool
    markdown: str
    sections: tuple[InfoSection, ...]


def load_terminal_info_markdown() -> str:
    """Read the packaged MCP Terminal guide."""
    return files("mcp_terminal").joinpath("docs").joinpath("INFO.md").read_text(encoding="utf-8")


TERMINAL_INFO_MARKDOWN = load_terminal_info_markdown()


def _normalize_section_markdown(lines: list[str]) -> str:
    text = "\n".join(lines).strip()
    return f"{text}\n" if text else ""


def _split_terminal_info_sections(markdown: str) -> tuple[InfoSection, ...]:
    """Split the packaged guide into top-level ``##`` sections."""
    preamble: list[str] = []
    current_title: str | None = None
    current_lines: list[str] = []
    sections: list[InfoSection] = []

    for line in markdown.splitlines():
        if line.startswith("## "):
            if current_title is not None:
                sections.append(
                    InfoSection(
                        title=current_title,
                        markdown=_normalize_section_markdown(current_lines),
                    )
                )
            current_title = line[3:].strip()
            current_lines = []
            if preamble:
                current_lines.extend(preamble)
                preamble = []
            current_lines.append(line)
            continue
        if current_title is None:
            preamble.append(line)
        else:
            current_lines.append(line)

    if current_title is None:
        return (
            InfoSection(title="Guide", markdown=_normalize_section_markdown(preamble)),
        )

    sections.append(
        InfoSection(
            title=current_title,
            markdown=_normalize_section_markdown(current_lines),
        )
    )
    return tuple(sections)


TERMINAL_INFO_SECTIONS = _split_terminal_info_sections(TERMINAL_INFO_MARKDOWN)


def terminal_info_total_pages(page_size: int) -> int:
    """Return the number of pages for *page_size* sections per page."""
    if page_size < 1 or page_size > MAX_INFO_PAGE_SIZE:
        raise ValueError("page_size out of range")
    return max(1, math.ceil(len(TERMINAL_INFO_SECTIONS) / page_size))


def paginate_terminal_info(*, page: int, page_size: int) -> InfoPage:
    """Return one page of the packaged guide."""
    if page < 1:
        raise ValueError("page must be >= 1")
    total_pages = terminal_info_total_pages(page_size)
    if page > total_pages:
        raise ValueError("page out of range")

    start = (page - 1) * page_size
    end = start + page_size
    sections = TERMINAL_INFO_SECTIONS[start:end]
    markdown = "\n\n".join(section.markdown.strip() for section in sections if section.markdown.strip())
    if markdown:
        markdown = f"{markdown}\n"
    return InfoPage(
        page=page,
        page_size=page_size,
        total_sections=len(TERMINAL_INFO_SECTIONS),
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
        markdown=markdown,
        sections=sections,
    )

TERMINAL_INFO_LIFECYCLE = [
    "Create a Code Analysis Server session with session_create.",
    "Create or reopen terminal state with terminal_session_create.",
    "Run sandbox commands with terminal_run and poll terminal_get_status.",
    "Read command output with terminal_read or terminal_tail.",
    "Attach an interactive PTY only to a kept sandbox container when needed.",
    "Use terminal_host_exec only for configured real-host commands.",
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
