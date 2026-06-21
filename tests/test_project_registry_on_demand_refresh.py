"""Tests for on-demand project registry refresh (BUG-MCPTERM-001)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_terminal.runtime_context import (
    configure_project_registry_sources,
    refresh_project_registry,
    registry_list_watch_layout,
    registry_resolve_project,
    set_terminal_services,
)
from mcp_terminal.services.project_registry import ProjectRegistry
from mcp_terminal.services.session_store import SessionStore


def _write_projectid(project_dir: Path, project_id: str) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "projectid").write_text(
        json.dumps({"id": project_id, "description": "test"}),
        encoding="utf-8",
    )


def _app_config(anchor: Path) -> dict:
    return {
        "watch_dirs": {"directories": [str(anchor)]},
        "code_analysis": {"enabled": False},
    }


@pytest.fixture
def registry_setup(tmp_path: Path):
    anchor = tmp_path / "watch"
    anchor.mkdir()
    config_path = tmp_path / "term_server.json"
    config_path.write_text("{}", encoding="utf-8")
    app_config = _app_config(anchor)

    reg = ProjectRegistry([anchor])
    reg.build()
    store = SessionStore()
    set_terminal_services(session_store=store, project_registry=reg)
    configure_project_registry_sources(
        config_path=config_path,
        get_app_config=lambda: app_config,
    )
    return anchor, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def test_registry_resolve_rescans_on_miss(registry_setup: tuple[Path, str]) -> None:
    anchor, project_id = registry_setup
    _write_projectid(anchor / "late_project", project_id)

    first = registry_resolve_project(project_id)
    assert first.success is True
    assert first.project_dir == (anchor / "late_project").resolve()


def test_refresh_project_registry_updates_layout(registry_setup: tuple[Path, str]) -> None:
    anchor, project_id = registry_setup
    _write_projectid(anchor / "late_project", project_id)

    assert registry_list_watch_layout()["totals"]["enabled_project_count"] == 0
    assert refresh_project_registry() is True
    layout = registry_list_watch_layout()
    assert layout["totals"]["enabled_project_count"] == 1
    assert layout["watch_directories"][0]["projects"][0]["project_id"] == project_id
