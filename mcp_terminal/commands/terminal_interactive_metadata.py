"""Shared metadata builders for sandbox interactive shell commands."""

from __future__ import annotations

from typing import Any, Dict, Type

from mcp_terminal.commands.metadata_common import (
    CASMGR_SESSION_ERROR_CASES,
    merge_error_cases,
)

_EXAMPLE_PROJECT = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_EXAMPLE_SESSION = "46ce9394-01ca-4440-9c03-c4a7466c4ec5"
_EXAMPLE_SHELL = f"{_EXAMPLE_PROJECT}:{_EXAMPLE_SESSION}"


def interactive_metadata(
    cls: Type[Any],
    *,
    detailed_description: str,
    parameters: Dict[str, Dict[str, Any]],
    success_data: Dict[str, str],
    usage_examples: list[dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": detailed_description,
        "parameters": parameters,
        "return_value": {
            "success": {
                "description": "Interactive sandbox shell operation result.",
                "data": success_data,
                "example": {"success": True, "data": success_data},
            },
            "error": {
                "description": "Unknown session/container/shell or invalid operation.",
                "code": "CONTAINER_NOT_RUNNING",
                "message": "Stable error code string.",
                "details": "Optional field hint from validation.",
            },
        },
        "usage_examples": usage_examples,
        "error_cases": merge_error_cases(
            {
                "CONTAINER_NOT_RUNNING": {
                    "description": "No kept sandbox container is running for this session.",
                    "message": "CONTAINER_NOT_RUNNING",
                    "solution": "Run terminal_run with keep_container true before attach.",
                },
                "NOT_FOUND": {
                    "description": "The requested interactive shell does not exist.",
                    "message": "NOT_FOUND",
                    "solution": "Call terminal_attach first and reuse the returned shell_id.",
                },
                "SHELL_EXITED": {
                    "description": "The PTY process has already exited.",
                    "message": "SHELL_EXITED",
                    "solution": "Call terminal_attach again to open a fresh shell.",
                },
                "INVALID_SESSION": {
                    "description": "No session directory for project_id plus session_id.",
                    "message": "INVALID_SESSION",
                    "solution": "Call terminal_session_create before terminal_attach.",
                },
            },
            CASMGR_SESSION_ERROR_CASES,
        ),
        "best_practices": [
            "Use terminal_run with keep_container true to create the sandbox first.",
            "Use terminal_read_shell with offsets to consume incremental PTY output.",
            "Detach shells when finished so the service can release the PTY process.",
        ],
    }


def project_param(required: bool = True) -> Dict[str, Any]:
    return {
        "description": "Project UUID4 used for the terminal session.",
        "type": "string",
        "required": required,
        "examples": [_EXAMPLE_PROJECT],
    }


def session_param(required: bool = True) -> Dict[str, Any]:
    return {
        "description": "Session UUID4 from terminal_session_create.",
        "type": "string",
        "required": required,
        "examples": [_EXAMPLE_SESSION],
    }


def shell_param(required: bool = True) -> Dict[str, Any]:
    return {
        "description": "Interactive shell id returned by terminal_attach.",
        "type": "string",
        "required": required,
        "examples": [_EXAMPLE_SHELL],
    }
