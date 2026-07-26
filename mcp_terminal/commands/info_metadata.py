"""Extended metadata for the MCP Terminal ``info`` command."""

from __future__ import annotations

from typing import Any, Dict, Type

from mcp_terminal.commands.info_resources import (
    DEFAULT_INFO_PAGE_SIZE,
    MAX_INFO_PAGE_SIZE,
    TERMINAL_INFO_MARKDOWN,
)


def get_info_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": TERMINAL_INFO_MARKDOWN,
        "parameters": {
            "page": {
                "description": "1-based guide page number.",
                "type": "integer",
                "required": False,
                "default": 1,
                "minimum": 1,
            },
            "page_size": {
                "description": "Number of top-level guide sections per page.",
                "type": "integer",
                "required": False,
                "default": DEFAULT_INFO_PAGE_SIZE,
                "minimum": 1,
                "maximum": MAX_INFO_PAGE_SIZE,
            },
        },
        "return_value": {
            "success": {
                "description": "Structured MCP Terminal guide with paginated markdown and examples.",
                "data": {
                    "guide_version": "Guide semver string.",
                    "package": "Project/debian package names and version.",
                    "summary": "One-line lifecycle summary.",
                    "markdown": "Current paginated markdown slice.",
                    "full_markdown": "Full prose guide for clients that need one-shot export.",
                    "lifecycle": "Ordered high-level workflow steps.",
                    "registered_commands": (
                        "Live MCP command catalog: name, version, description, category."
                    ),
                    "sections": "Paginated list of top-level guide sections for this page.",
                    "pagination": "Navigation metadata: page, page_size, total_pages, has_prev, has_next.",
                    "docs": "Package documentation paths.",
                },
                "example": {
                    "success": True,
                    "data": {
                        "guide_version": "1.2",
                        "package": {
                            "project_name": "mcp-terminal",
                            "debian_package": "mcp-terminal-docker",
                            "version": "0.1.40",
                            "service_image_tag": "0.1.40",
                        },
                        "summary": (
                            "CA session_create -> terminal_session_create -> "
                            "terminal_run -> status/read -> cleanup"
                        ),
                        "pagination": {
                            "page": 1,
                            "page_size": 4,
                            "total_pages": 3,
                            "total_sections": 11,
                            "has_prev": False,
                            "has_next": True,
                        },
                    },
                },
            },
            "error": {
                "description": "Guide could not be returned.",
                "code": "COMMAND_ERROR",
                "message": "Human-readable failure description.",
            },
        },
        "usage_examples": [
            {
                "description": "Load first guide page",
                "command": {"page": 1, "page_size": 4},
                "explanation": (
                    "Returns one page of markdown plus pagination metadata, lifecycle "
                    "steps, command catalog, and documentation paths."
                ),
            },
            {
                "description": "Read the next guide page",
                "command": {"page": 2, "page_size": 4},
                "explanation": (
                    "Use pagination to walk large guide content without returning the "
                    "entire markdown payload on every call."
                ),
            },
        ],
        "error_cases": {
            "VALIDATION_ERROR": {
                "description": "Unexpected parameter or invalid pagination value.",
                "message": "VALIDATION_ERROR",
                "solution": "Call info with page/page_size only, using positive integers.",
            },
            "PAGE_OUT_OF_RANGE": {
                "description": "Requested guide page is beyond the available range.",
                "message": "PAGE_OUT_OF_RANGE",
                "solution": "Read pagination.total_pages from a successful response and retry.",
            },
            "COMMAND_ERROR": {
                "description": "Command failed unexpectedly.",
                "message": "COMMAND_ERROR",
                "solution": "See server logs and retry.",
            },
        },
        "best_practices": [
            "Call info once before the first terminal task in a session.",
            "Use page/page_size instead of fetching the full guide repeatedly.",
            "Use help(command=...) for exact parameter schemas after reading the guide.",
            "Use terminal_run for sandbox work and terminal_host_exec only when needed.",
        ],
    }
