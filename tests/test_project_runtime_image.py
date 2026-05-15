"""Tests for per-project runtime image state and session bootstrap wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from mcp_terminal.services.project_runtime_image import (
    runtime_fingerprint,
    resolve_execution_image,
    verify_runtime_image_state,
)
from mcp_terminal.services.session_bootstrap import run_session_runtime_bootstrap


def test_runtime_fingerprint_changes_with_requirements(tmp_path: Path) -> None:
    a = runtime_fingerprint(tmp_path, image_profile="python_dev_3_12")
    (tmp_path / "requirements.txt").write_text("x\n", encoding="utf-8")
    b = runtime_fingerprint(tmp_path, image_profile="python_dev_3_12")
    assert a != b


def test_resolve_uses_stock_without_requirements(tmp_path: Path) -> None:
    ref, err = resolve_execution_image(
        tmp_path,
        project_id="00000000-0000-4000-8000-000000000001",
        image_profile="python_dev_3_12",
        stock_image_ref="ghcr.io/stock:1",
    )
    assert ref == "ghcr.io/stock:1" and err is None


def test_verify_runtime_false_without_state(tmp_path: Path) -> None:
    ok, reason = verify_runtime_image_state(tmp_path)
    assert ok is False and reason == "no_state"


@patch("mcp_terminal.services.project_runtime_image.ensure_project_runtime_image")
def test_run_session_runtime_bootstrap_maps_success(mock_ensure, tmp_path: Path) -> None:
    mock_ensure.return_value = (True, True, 0, "image_verified")
    sess = tmp_path / "s"
    sess.mkdir()
    br = run_session_runtime_bootstrap(
        tmp_path,
        project_id="00000000-0000-4000-8000-000000000001",
        session_dir=sess,
        image_profile="python_dev_3_12",
        timeout_seconds=60,
    )
    assert br.success and br.skipped and br.exit_code == 0
