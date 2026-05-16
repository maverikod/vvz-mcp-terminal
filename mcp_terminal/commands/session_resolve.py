"""Shared session lookup for terminal_* commands."""

from __future__ import annotations

from typing import Optional, Tuple

from mcp_terminal.runtime_context import get_session_store
from mcp_terminal.services.session_ids import validate_uuid4_field
from mcp_terminal.services.session_store import SessionRecord


def resolve_session(
    project_id: str,
    session_id: str,
) -> Tuple[Optional[SessionRecord], Optional[str]]:
    """Validate UUID4 pair and return ``(record, error_code)``."""
    pid = project_id.strip()
    sid = session_id.strip()
    for field, value in (("project_id", pid), ("session_id", sid)):
        err = validate_uuid4_field(value, field)
        if err:
            return None, err
    record = get_session_store().get_session(pid, sid)
    if record is None:
        return None, "INVALID_SESSION"
    return record, None
