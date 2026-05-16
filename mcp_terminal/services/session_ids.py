"""UUID4 validation for external session and project identifiers."""

from __future__ import annotations

import re
from typing import Optional

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def is_valid_uuid4(value: str) -> bool:
    """Return True if ``value`` is a UUID4 string."""
    return bool(_UUID4_RE.match(value.strip()))


def validate_uuid4_field(value: str, field: str) -> Optional[str]:
    """Return stable error code when invalid, else None."""
    if is_valid_uuid4(value):
        return None
    if field == "project_id":
        return "INVALID_PROJECT_ID"
    if field == "session_id":
        return "INVALID_SESSION_ID"
    return "INVALID_UUID"
