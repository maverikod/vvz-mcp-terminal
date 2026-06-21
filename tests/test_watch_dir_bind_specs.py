"""Tests for watch_dir_bind_specs helper."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1] / "docker" / "pkg"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))
from watch_dir_bind_specs import watch_dir_bind_specs, watch_dir_supplementary_gids  # noqa: E402


def test_watch_dir_bind_specs_from_config(tmp_path: Path) -> None:
    cfg = tmp_path / "term_server.json"
    cfg.write_text(
        json.dumps({"watch_dirs": {"directories": ["/var/casmgr/watch_catalog"]}}),
        encoding="utf-8",
    )
    specs = watch_dir_bind_specs(cfg)
    assert specs == ["/var/casmgr/watch_catalog:/var/casmgr/watch_catalog"]


def test_watch_dir_bind_specs_skips_extra_binds_duplicate(tmp_path: Path) -> None:
    cfg = tmp_path / "term_server.json"
    cfg.write_text(
        json.dumps({"watch_dirs": {"directories": ["/var/casmgr/watch_catalog"]}}),
        encoding="utf-8",
    )
    specs = watch_dir_bind_specs(
        cfg,
        extra_binds="/var/casmgr/watch_catalog:/var/casmgr/watch_catalog",
    )
    assert specs == []


def test_watch_dir_bind_specs_skips_placeholders(tmp_path: Path) -> None:
    cfg = tmp_path / "term_server.json"
    cfg.write_text(
        json.dumps({"watch_dirs": {"directories": ["WATCH_DIRS_ROOT"]}}),
        encoding="utf-8",
    )
    assert watch_dir_bind_specs(cfg) == []


def test_watch_dir_supplementary_gids_for_mode_750(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    os.chmod(catalog, 0o750)
    cfg = tmp_path / "term_server.json"
    cfg.write_text(json.dumps({"watch_dirs": {"directories": [str(catalog)]}}), encoding="utf-8")
    gids = watch_dir_supplementary_gids(cfg)
    assert catalog.stat().st_gid in gids


def test_watch_dir_supplementary_gids_skips_world_readable(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    os.chmod(catalog, 0o755)
    cfg = tmp_path / "term_server.json"
    cfg.write_text(json.dumps({"watch_dirs": {"directories": [str(catalog)]}}), encoding="utf-8")
    assert watch_dir_supplementary_gids(cfg) == []
