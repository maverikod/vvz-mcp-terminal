"""
ErrorContract: stable error codes for mcp_terminal (C-015).

These codes are returned on request rejection or execution failure.
Their meaning is stable across versions; callers handle them programmatically.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Optional


class ErrorCode:
    """Stable error code constants for mcp_terminal (C-015).

    Each constant maps to exactly one rejection condition.
    Do not change the string values; they are part of the public contract.
    """

    PROJECT_NOT_FOUND: str = "PROJECT_NOT_FOUND"
    PROJECT_DELETED: str = "PROJECT_DELETED"
    PROJECT_PAUSED: str = "PROJECT_PAUSED"
    PROJECT_PATH_OUT_OF_SCOPE: str = "PROJECT_PATH_OUT_OF_SCOPE"
    INVALID_CWD: str = "INVALID_CWD"
    INVALID_COMMAND: str = "INVALID_COMMAND"
    INVALID_SESSION: str = "INVALID_SESSION"
    INVALID_SESSION_ID: str = "INVALID_SESSION_ID"
    INVALID_PROJECT_ID: str = "INVALID_PROJECT_ID"
    SESSION_PROJECT_MISMATCH: str = "SESSION_PROJECT_MISMATCH"
    SESSION_STATE_CORRUPT: str = "SESSION_STATE_CORRUPT"
    WORKSPACE_WRITE_NOT_ALLOWED: str = "WORKSPACE_WRITE_NOT_ALLOWED"
    IMAGE_PROFILE_NOT_ALLOWED: str = "IMAGE_PROFILE_NOT_ALLOWED"
    MODE_NOT_ALLOWED: str = "MODE_NOT_ALLOWED"
    NETWORK_MODE_NOT_ALLOWED: str = "NETWORK_MODE_NOT_ALLOWED"
    TIMEOUT_EXCEEDED: str = "TIMEOUT_EXCEEDED"
    OUTPUT_LIMIT_EXCEEDED: str = "OUTPUT_LIMIT_EXCEEDED"
    CONTAINER_CREATE_FAILED: str = "CONTAINER_CREATE_FAILED"
    CONTAINER_EXEC_FAILED: str = "CONTAINER_EXEC_FAILED"
    CONTAINER_CLEANUP_FAILED: str = "CONTAINER_CLEANUP_FAILED"
    HOST_EXECUTION_DISABLED: str = "HOST_EXECUTION_DISABLED"
    HOST_COMMAND_NOT_ALLOWED: str = "HOST_COMMAND_NOT_ALLOWED"
    HOST_FORBIDDEN_COMMAND: str = "HOST_FORBIDDEN_COMMAND"


ALL_ERROR_CODES: FrozenSet[str] = frozenset(
    v for k, v in vars(ErrorCode).items() if not k.startswith("_")
)


@dataclass(frozen=True)
class TerminalError:
    """Structured error response for mcp_terminal.

    error_code is always a value from ErrorCode. message is human-readable
    and not stable across versions.
    """

    error_code: str  # Stable ErrorContract code from ErrorCode constants.
    message: str  # Human-readable detail; not stable across versions.
    field: Optional[str] = (
        None  # Name of the request field that triggered this error, if applicable.
    )
