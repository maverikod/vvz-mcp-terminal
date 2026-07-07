"""Extended metadata for the MCP Terminal ``info`` command."""

from __future__ import annotations

from typing import Any, Dict, Type

from mcp_terminal.commands.info_resources import TERMINAL_INFO_MARKDOWN


def get_info_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": TERMINAL_INFO_MARKDOWN,
        "parameters": {},
        "return_value": {
            "success": {
                "description": "Structured MCP Terminal guide with markdown and examples.",
                "data": {
                    "guide_version": "Guide semver string.",
                    "package": "Project/debian package names and version.",
                    "summary": "One-line lifecycle summary.",
                    "markdown": "Full prose guide, same as detailed_description.",
                    "lifecycle": "Ordered high-level workflow steps.",
                    "registered_commands": (
                        "Live MCP command catalog: name, version, description, category."
                    ),
                    "docs": "Package documentation paths.",
                },
                "example": {
                    "success": True,
                    "data": {
                        "guide_version": "1.1",
                        "package": {
                            "project_name": "mcp-terminal",
                            "debian_package": "mcp-terminal-docker",
                            "version": "0.1.31",
                            "service_image_tag": "0.1.31",
                        },
                        "summary": (
                            "CA session_create -> terminal_session_create -> "
                            "terminal_run -> status/read -> cleanup"
                        ),
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
                "description": "Load full MCP Terminal guide",
                "command": {},
                "explanation": (
                    "No parameters. Returns markdown, lifecycle steps, command "
                    "catalog, and documentation paths."
                ),
            },
        ],
        "error_cases": {
            "VALIDATION_ERROR": {
                "description": "Unexpected parameter supplied to the zero-argument command.",
                "message": "VALIDATION_ERROR",
                "solution": "Call info with an empty params object.",
            },
            "COMMAND_ERROR": {
                "description": "Command failed unexpectedly.",
                "message": "COMMAND_ERROR",
                "solution": "See server logs and retry.",
            },
        },
        "best_practices": [
            "Call info once before the first terminal task in a session.",
            "Use help(command=...) for exact parameter schemas after reading the guide.",
            "Use terminal_run for sandbox work and terminal_host_exec only when needed.",
        ],
    }
