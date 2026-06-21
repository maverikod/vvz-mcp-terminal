"""Shared metadata fragments for terminal_* commands."""

from __future__ import annotations

from typing import Any, Dict

_METADATA_REQUIRED_KEYS = frozenset(
    {
        "name",
        "version",
        "description",
        "category",
        "author",
        "email",
        "detailed_description",
        "parameters",
        "return_value",
        "usage_examples",
        "error_cases",
        "best_practices",
    }
)

_ERROR_CASE_ENTRY_KEYS = frozenset({"description", "message", "solution"})

CASMGR_SESSION_ERROR_CASES: Dict[str, Dict[str, str]] = {
    "CLIENT_SESSION_NOT_FOUND": {
        "description": "session_id is not registered on code-analysis-server (casmgr).",
        "message": "CLIENT_SESSION_NOT_FOUND",
        "solution": (
            "Call casmgr session_create first; reuse the returned session_id in "
            "terminal_session_create."
        ),
    },
    "SUBORDINATE_SESSION_NOT_LINKED": {
        "description": (
            "No subordinate link between this parent session and the terminal server "
            "instance."
        ),
        "message": "SUBORDINATE_SESSION_NOT_LINKED",
        "solution": (
            "Call terminal_session_create with the same session_id after casmgr "
            "session_create."
        ),
    },
    "CODE_ANALYSIS_UNAVAILABLE": {
        "description": "Cannot reach code-analysis-server or config is incomplete.",
        "message": "CODE_ANALYSIS_UNAVAILABLE",
        "solution": (
            "Verify code_analysis host/port/ssl in term_server.json and casmgr "
            "availability."
        ),
    },
}


def merge_error_cases(*parts: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """Merge error-case dicts; later parts override earlier keys."""
    merged: Dict[str, Dict[str, str]] = {}
    for part in parts:
        merged.update(part)
    return merged


def validate_metadata_shape(metadata: Dict[str, Any], *, command_name: str) -> None:
    """Raise AssertionError when metadata violates metadatastd required fields."""
    missing = _METADATA_REQUIRED_KEYS - set(metadata.keys())
    if missing:
        raise AssertionError(f"{command_name}: metadata missing keys {sorted(missing)}")
    error_cases = metadata.get("error_cases")
    if not isinstance(error_cases, dict):
        raise AssertionError(f"{command_name}: error_cases must be a dict")
    for code, entry in error_cases.items():
        if not isinstance(entry, dict):
            raise AssertionError(f"{command_name}: error_cases[{code!r}] must be a dict")
        entry_missing = _ERROR_CASE_ENTRY_KEYS - set(entry.keys())
        if entry_missing:
            raise AssertionError(
                f"{command_name}: error_cases[{code!r}] missing {sorted(entry_missing)}"
            )
