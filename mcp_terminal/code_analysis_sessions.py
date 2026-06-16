"""
Casmgr client-session and subordinate-session RPC (sync façades).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from mcp_terminal.code_analysis_rpc import (
    CodeAnalysisRpcError,
    call_code_analysis_sync,
    code_analysis_section,
    terminal_instance_uuid,
)


def session_validate_sync(
    app_config: Dict[str, Any],
    session_id: str,
    *,
    touch: bool = False,
) -> Dict[str, Any]:
    """Call casmgr ``session_validate``."""
    section = code_analysis_section(app_config)
    params: Dict[str, Any] = {"session_id": session_id.strip()}
    if touch:
        params["touch"] = True
    return call_code_analysis_sync(section, "session_validate", params)


def subordinate_session_create_sync(
    app_config: Dict[str, Any],
    *,
    parent_session_id: str,
    server_uuid: Optional[str] = None,
    comment: str = "mcp-terminal session link",
) -> Dict[str, Any]:
    """Call casmgr ``subordinate_session_create`` (idempotent on duplicate)."""
    section = code_analysis_section(app_config)
    suuid = (server_uuid or terminal_instance_uuid(app_config)).strip()
    params: Dict[str, Any] = {
        "parent_session_id": parent_session_id.strip(),
        "server_uuid": suuid,
        "comment": comment,
    }
    try:
        return call_code_analysis_sync(section, "subordinate_session_create", params)
    except CodeAnalysisRpcError as exc:
        if exc.code == "SUBORDINATE_SESSION_ALREADY_EXISTS":
            return {"already_exists": True}
        raise


def subordinate_session_get_sync(
    app_config: Dict[str, Any],
    *,
    parent_session_id: str,
    server_uuid: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return subordinate link row or ``None`` when ``SUBORDINATE_SESSION_NOT_FOUND``."""
    section = code_analysis_section(app_config)
    suuid = (server_uuid or terminal_instance_uuid(app_config)).strip()
    try:
        return call_code_analysis_sync(
            section,
            "subordinate_session_get",
            {
                "parent_session_id": parent_session_id.strip(),
                "server_uuid": suuid,
            },
        )
    except CodeAnalysisRpcError as exc:
        if exc.code == "SUBORDINATE_SESSION_NOT_FOUND":
            return None
        raise


def subordinate_session_delete_sync(
    app_config: Dict[str, Any],
    *,
    parent_session_id: str,
    server_uuid: Optional[str] = None,
) -> None:
    """Call casmgr ``subordinate_session_delete`` (ignore not-found)."""
    section = code_analysis_section(app_config)
    suuid = (server_uuid or terminal_instance_uuid(app_config)).strip()
    try:
        call_code_analysis_sync(
            section,
            "subordinate_session_delete",
            {
                "parent_session_id": parent_session_id.strip(),
                "server_uuid": suuid,
            },
        )
    except CodeAnalysisRpcError as exc:
        if exc.code == "SUBORDINATE_SESSION_NOT_FOUND":
            return
        raise
