"""Tests for terminal_list_watch and ProjectRegistry.list_watch_layout."""

from __future__ import annotations

import json
from pathlib import Path

from mcp_terminal.services.project_registry import ProjectRegistry


def test_list_watch_layout_groups_by_anchor(tmp_path: Path) -> None:
    anchor = tmp_path / "ws"
    proj = anchor / "myapp"
    proj.mkdir(parents=True)
    (proj / "projectid").write_text(
        json.dumps(
            {
                "id": "11111111-1111-4111-8111-111111111111",
                "description": "Test app",
            }
        ),
        encoding="utf-8",
    )
    reg = ProjectRegistry([anchor])
    reg.build()
    layout = reg.list_watch_layout()
    assert layout["totals"]["watch_directory_count"] == 1
    assert layout["totals"]["enabled_project_count"] == 1
    assert len(layout["watch_directories"]) == 1
    row = layout["watch_directories"][0]
    assert row["directory"] == str(anchor.resolve())
    assert len(row["projects"]) == 1
    assert row["projects"][0]["project_id"] == "11111111-1111-4111-8111-111111111111"
    assert row["projects"][0]["disabled"] is False


def test_projectid_on_anchor_directory_is_indexed(tmp_path: Path) -> None:
    """When the watch anchor is the project root, ``projectid`` in that dir counts."""
    anchor = tmp_path / "repo"
    anchor.mkdir()
    (anchor / "projectid").write_text(
        json.dumps(
            {
                "id": "22222222-2222-4222-8222-222222222222",
                "description": "Root marker",
            }
        ),
        encoding="utf-8",
    )
    reg = ProjectRegistry([anchor])
    reg.build()
    res = reg.resolve("22222222-2222-4222-8222-222222222222")
    assert res.success is True
    assert res.project_dir == anchor.resolve()
    layout = reg.list_watch_layout()
    assert layout["totals"]["enabled_project_count"] == 1
    assert layout["watch_directories"][0]["directory"] == str(anchor.resolve())


def test_empty_registry_list_watch_layout() -> None:
    reg = ProjectRegistry([])
    reg.build()
    layout = reg.list_watch_layout()
    assert layout["watch_directories"] == []
    assert layout["totals"]["watch_directory_count"] == 0
    assert layout["totals"]["enabled_project_count"] == 0
