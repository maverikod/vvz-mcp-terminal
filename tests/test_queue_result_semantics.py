"""
Unit tests for QueueResultSemantics invariant (C-011).

Verifies that terminal_status is derived correctly from queue_status,
exit_code, and timed_out. Queue completed != terminal success.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest  # noqa: F401


def _derive_terminal_status(
    queue_status: str,
    exit_code: int | None,
    timed_out: bool | None,
) -> str:
    """Replicate the QueueResultSemantics logic from terminal_get_status."""
    timed_out = timed_out or False
    if queue_status == "completed" and exit_code == 0 and not timed_out:
        return "success"
    elif queue_status == "completed" and timed_out:
        return "timed_out"
    elif queue_status == "completed":
        return "failure"
    else:
        return queue_status


def test_completed_exit0_not_timed_out_is_success() -> None:
    assert _derive_terminal_status("completed", 0, False) == "success"


def test_completed_exit1_is_failure() -> None:
    assert _derive_terminal_status("completed", 1, False) == "failure"


def test_completed_timed_out_is_timed_out() -> None:
    assert _derive_terminal_status("completed", None, True) == "timed_out"


def test_pending_is_pending() -> None:
    assert _derive_terminal_status("pending", None, None) == "pending"


def test_running_is_running() -> None:
    assert _derive_terminal_status("running", None, None) == "running"


def test_failed_is_failed() -> None:
    assert _derive_terminal_status("failed", None, None) == "failed"


def test_stopped_is_stopped() -> None:
    assert _derive_terminal_status("stopped", None, None) == "stopped"


def test_completed_exit0_timed_out_true_is_timed_out() -> None:
    """Even with exit_code=0, timed_out=True means timed_out status."""
    assert _derive_terminal_status("completed", 0, True) == "timed_out"
