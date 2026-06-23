"""Shared JSON-schema property fragments for terminal_* commands."""

from __future__ import annotations

from typing import Any, Dict, Optional


def schema_project_id() -> Dict[str, Any]:
    return {
        "type": "string",
        "description": (
            "Project UUID4. Use terminal_list_watch to discover valid project_id values."
        ),
    }


def schema_session_id() -> Dict[str, Any]:
    return {
        "type": "string",
        "description": "Session UUID4 from terminal_session_create.",
    }


def schema_seq(*, description: Optional[str] = None) -> Dict[str, Any]:
    return {
        "type": "integer",
        "minimum": 1,
        "description": description
        or (
            "Session-local command sequence number from terminal_run or "
            "terminal_host_exec."
        ),
    }
