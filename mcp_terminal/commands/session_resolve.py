"""Shared session lookup for terminal_* commands."""

from __future__ import annotations

from typing import Optional, Tuple

from mcp_proxy_adapter.config import get_config

from mcp_terminal.code_analysis_rpc import CodeAnalysisRpcError
from mcp_terminal.code_analysis_sessions import (
    session_validate_sync,
    subordinate_session_get_sync,
)
from mcp_terminal.errors import ErrorCode
from mcp_terminal.runtime_context import get_session_store, registry_resolve_project
from mcp_terminal.services.session_ids import validate_uuid4_field
from mcp_terminal.services.session_store import SessionRecord


def _app_config() -> dict:
    data = getattr(get_config(), "config_data", None)
    return data if isinstance(data, dict) else {}


def _map_casmgr_error(exc: CodeAnalysisRpcError) -> str:
    if exc.code == "SESSION_NOT_FOUND":
        return ErrorCode.CLIENT_SESSION_NOT_FOUND
    if exc.code == "CODE_ANALYSIS_UNAVAILABLE":
        return ErrorCode.CODE_ANALYSIS_UNAVAILABLE
    return ErrorCode.CODE_ANALYSIS_UNAVAILABLE


def resolve_session(
    project_id: str,
    session_id: str,
    *,
    touch: bool = False,
) -> Tuple[Optional[SessionRecord], Optional[str]]:
    """Validate UUID4 pair, local session, and casmgr client + subordinate link."""
    pid = project_id.strip()
    sid = session_id.strip()
    for field, value in (("project_id", pid), ("session_id", sid)):
        err = validate_uuid4_field(value, field)
        if err:
            return None, err
    store = get_session_store()
    record = store.get_session(pid, sid)
    if record is None:
        # Server restart empties the in-memory store while the session
        # survives on disk (bug e27f23f4) - lazily re-adopt before rejecting.
        # A registry failure must not mask the INVALID_SESSION answer.
        try:
            resolved = registry_resolve_project(pid)
            if resolved.success and resolved.project_dir is not None:
                record = store.adopt_session(pid, sid, resolved.project_dir)
        except Exception:  # noqa: BLE001 - adoption is best-effort
            record = None
    if record is None:
        return None, ErrorCode.INVALID_SESSION

    app_config = _app_config()
    try:
        session_validate_sync(app_config, sid, touch=touch)
    except CodeAnalysisRpcError as exc:
        return None, _map_casmgr_error(exc)
    except ValueError:
        return None, ErrorCode.CODE_ANALYSIS_UNAVAILABLE

    try:
        link = subordinate_session_get_sync(app_config, parent_session_id=sid)
    except CodeAnalysisRpcError as exc:
        return None, _map_casmgr_error(exc)
    except ValueError:
        return None, ErrorCode.CODE_ANALYSIS_UNAVAILABLE

    if link is None:
        return None, ErrorCode.SUBORDINATE_SESSION_NOT_LINKED
    return record, None
